from __future__ import annotations

from uuid import uuid4

import pytest

from power_fault_analyzer.domain.aggregates.network import Network
from power_fault_analyzer.domain.entities.bus import Bus
from power_fault_analyzer.domain.entities.electrical_equipment import ElectricalEquipmentBase
from power_fault_analyzer.domain.entities.terminal import Terminal
from power_fault_analyzer.domain.enums.equipment_family import EquipmentFamily
from power_fault_analyzer.domain.enums.switching_device import (
    SwitchingDeviceKind,
)
from power_fault_analyzer.domain.enums.switching_device import (
    SwitchPosition as DomainSwitchPosition,
)
from power_fault_analyzer.domain.value_objects.voltage import Voltage
from power_fault_analyzer.equipment.switching.switching_device import SwitchingDevice
from power_fault_analyzer.operations import (
    ACLoadFlowCaseResult,
    OperatingScenario,
    RestorationAssessmentService,
    RestorationAssessmentStatus,
    RestorationPlanner,
    SwitchingSequenceService,
    SwitchPosition,
    scenario_fingerprint,
)


class _Stub(ElectricalEquipmentBase):
    __slots__ = ()

    def __init__(self, *, equipment_id, name, terminals, family):
        super().__init__(id=equipment_id, name=name, terminals=terminals, family=family)


def _restoration_fixture():
    voltage = Voltage.from_kv(13.8)
    buses = [Bus(f"BUS-{name}", voltage) for name in "ABC"]
    network = Network("Restoration assessment fixture")
    for bus in buses:
        network.add_bus(bus)

    source_id = uuid4()
    source_terminal = Terminal(source_id, "GRID", voltage)
    network.add_equipment(_Stub(
        equipment_id=source_id, name="GRID", terminals=(source_terminal,),
        family=EquipmentFamily.SOURCE,
    ))
    network.connect(source_terminal.id, buses[0].id)

    line_id = uuid4()
    line_terminals = (Terminal(line_id, "FROM", voltage), Terminal(line_id, "TO", voltage))
    network.add_equipment(_Stub(
        equipment_id=line_id, name="LINE-A-B", terminals=line_terminals,
        family=EquipmentFamily.TRANSMISSION,
    ))
    network.connect(line_terminals[0].id, buses[0].id)
    network.connect(line_terminals[1].id, buses[1].id)

    switch_id = uuid4()
    switch_terminals = (Terminal(switch_id, "A", voltage), Terminal(switch_id, "B", voltage))
    network.add_equipment(SwitchingDevice(
        id=switch_id, name="CB-B-C", terminals=switch_terminals,
        device_kind=SwitchingDeviceKind.CIRCUIT_BREAKER,
        position=DomainSwitchPosition.CLOSED,
    ))
    network.connect(switch_terminals[0].id, buses[1].id)
    network.connect(switch_terminals[1].id, buses[2].id)

    initial = OperatingScenario(
        name="CB open",
        switch_positions={switch_id: SwitchPosition.OPEN},
    )
    plan = RestorationPlanner().propose(
        network, initial, target_bus_ids=(buses[2].id,)
    )
    final_scenario = SwitchingSequenceService().simulate(network, plan.sequence).final_scenario
    fingerprint = scenario_fingerprint(network, final_scenario)
    energized = plan.projected_topology.energized_bus_ids
    bus_results = {bus_id: 1.0 for bus_id in energized}
    base = ACLoadFlowCaseResult(
        case_id="base", network_id=network.id, scenario_fingerprint=fingerprint,
        converged=True, bus_voltages_pu=bus_results, branch_loading_pct={line_id: 72.0},
    )
    n1 = ACLoadFlowCaseResult(
        case_id="N-1:LINE-A-B", network_id=network.id, scenario_fingerprint=fingerprint,
        converged=True, bus_voltages_pu=bus_results, branch_loading_pct={line_id: 84.0},
    )
    return network, plan, line_id, fingerprint, base, n1


def test_restoration_assessment_accepts_complete_base_and_declared_n1_results():
    network, plan, line_id, _fingerprint, base, n1 = _restoration_fixture()

    result = RestorationAssessmentService().assess(
        network, plan, base,
        contingency_cases=(n1,),
        required_contingency_case_ids=("N-1:LINE-A-B",),
        required_branch_ids=(line_id,),
    )

    assert result.status is RestorationAssessmentStatus.FEASIBLE
    assert result.feasible
    assert result.cases_evaluated == ("base", "N-1:LINE-A-B")
    assert result.findings == ()


def test_known_branch_limit_violation_takes_precedence_over_missing_data():
    network, plan, line_id, _fingerprint, _base, n1 = _restoration_fixture()
    from dataclasses import replace

    overloaded_base = replace(
        n1, case_id="base", branch_loading_pct={line_id: 112.0},
        bus_voltages_pu={},
    )
    result = RestorationAssessmentService().assess(
        network, plan, overloaded_base, required_branch_ids=(line_id,),
    )

    assert result.status is RestorationAssessmentStatus.INFEASIBLE
    assert {item.code for item in result.findings} >= {
        "BRANCH_LOADING_LIMIT_VIOLATION", "BUS_VOLTAGE_MISSING"
    }


def test_missing_required_n1_case_is_indeterminate():
    network, plan, line_id, _fingerprint, base, _n1 = _restoration_fixture()

    result = RestorationAssessmentService().assess(
        network, plan, base,
        required_contingency_case_ids=("N-1:LINE-A-B",),
        required_branch_ids=(line_id,),
    )

    assert result.status is RestorationAssessmentStatus.INDETERMINATE
    assert any(item.code == "N1_CASE_MISSING" for item in result.findings)


def test_load_flow_result_must_match_network_scenario_fingerprint():
    network, plan, line_id, _fingerprint, base, _n1 = _restoration_fixture()
    from dataclasses import replace

    mismatched = replace(base, scenario_fingerprint="0" * 64)
    result = RestorationAssessmentService().assess(
        network, plan, mismatched, required_branch_ids=(line_id,)
    )

    assert result.status is RestorationAssessmentStatus.INDETERMINATE
    assert result.findings[0].code == "SCENARIO_FINGERPRINT_MISMATCH"


def test_invalid_limits_are_rejected():
    network, plan, _line_id, _fingerprint, base, _n1 = _restoration_fixture()
    with pytest.raises(ValueError, match="limits"):
        RestorationAssessmentService().assess(
            network, plan, base, voltage_min_pu=1.1, voltage_max_pu=0.9
        )
