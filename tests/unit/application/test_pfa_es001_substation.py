from __future__ import annotations

import json
from pathlib import Path

import pytest

from power_fault_analyzer.application.use_cases.network_editing import SetSwitchPosition
from power_fault_analyzer.application.use_cases.run_network_short_circuit_study import (
    NetworkStudyValidationError,
    RunNetworkShortCircuitStudy,
)
from power_fault_analyzer.application.use_cases.substation_engineering import (
    BuildPFAES001Substation,
    validate_substation_topology,
)
from power_fault_analyzer.domain.enums.bus_kind import BusKind
from power_fault_analyzer.domain.enums.fault_type import FaultType
from power_fault_analyzer.domain.enums.switching_device import SwitchPosition
from power_fault_analyzer.equipment.interfaces.unresolved_equipment import (
    UnresolvedEquipmentInterface,
)
from power_fault_analyzer.equipment.switching.switching_device import SwitchingDevice
from power_fault_analyzer.infrastructure.adapters.sequence_network_set_factory_adapter import (
    SequenceNetworkSetFactoryAdapter,
)
from power_fault_analyzer.infrastructure.adapters.short_circuit_solver_adapter import (
    NumericalShortCircuitSolverAdapter,
)
from power_fault_analyzer.infrastructure.persistence.json_network_document_repository import (
    JSONNetworkDocumentRepository,
)


def test_pfa_es001_builds_explicit_double_bus_switch_topology() -> None:
    built = BuildPFAES001Substation().execute()
    workspace = built.workspace
    network = workspace.network

    assert len(network.buses) == 8
    assert sum(bus.kind is BusKind.BUSBAR for bus in network.buses) == 2
    assert sum(bus.kind is BusKind.CONNECTION_NODE for bus in network.buses) == 6
    assert len(network.equipment) == 10
    assert sum(isinstance(item, SwitchingDevice) for item in network.equipment) == 8
    assert sum(isinstance(item, UnresolvedEquipmentInterface) for item in network.equipment) == 2
    assert len(network.connections) == 18
    assert len(workspace.diagram_symbols) == 10

    switches = {item.name: item for item in network.equipment if isinstance(item, SwitchingDevice)}
    assert switches["Q-LINE-DS-BB1"].position is SwitchPosition.CLOSED
    assert switches["Q-LINE-DS-BB2"].position is SwitchPosition.OPEN
    assert switches["Q-TR-DS-BB1"].position is SwitchPosition.CLOSED
    assert switches["Q-TR-DS-BB2"].position is SwitchPosition.OPEN
    assert built.validation.structurally_valid is True
    assert built.validation.study_ready is False
    assert all(item.connected_busbar_names == ("BB-220-1",) for item in built.validation.interfaces)
    assert all(item.unresolved_parameters for item in built.validation.interfaces)


def test_pfa_es001_sequence_adapter_collapses_closed_switches_and_blocks_missing_data() -> None:
    built = BuildPFAES001Substation().execute()
    network = built.workspace.network
    use_case = RunNetworkShortCircuitStudy(
        NumericalShortCircuitSolverAdapter(), SequenceNetworkSetFactoryAdapter()
    )

    with pytest.raises(NetworkStudyValidationError, match="SEQ-EQUIPMENT-MODEL-UNRESOLVED"):
        use_case.execute(
            network,
            fault_bus_id=next(bus.id for bus in network.buses if bus.name == "BB-220-1"),
            fault_type=FaultType.THREE_PHASE,
            fault_impedance_pu=0j,
            base_power_mva=100.0,
            project_name="PFA-ES-001",
        )

    # Exercise the topology adapter directly: 8 graphical/network bus records
    # reduce to two electrical nodes because six closed switch connections
    # join each bay to BB-220-1, while BB-220-2 remains isolated by open selectors.
    from power_fault_analyzer.domain.enums.sequence_type import SequenceType
    from power_fault_analyzer.network.sequence_networks.builder import SequenceNetworkBuilder
    from power_fault_analyzer.network.sequence_networks.models import SystemBaseSet

    base = SystemBaseSet.from_network(network, 100.0)
    positive = SequenceNetworkBuilder(base).build(network, SequenceType.POSITIVE)
    assert len(positive.nodes) == 2
    assert not positive.branches
    assert any(item.code == "SEQ-EQUIPMENT-MODEL-UNRESOLVED" for item in positive.diagnostics)


def test_switch_position_changes_topology_and_invalidates_double_bus_selection() -> None:
    workspace = BuildPFAES001Substation().execute().workspace
    network = workspace.network
    switch = next(
        item
        for item in network.equipment
        if isinstance(item, SwitchingDevice) and item.name == "Q-LINE-DS-BB2"
    )

    updated = SetSwitchPosition().execute(network, switch.id, SwitchPosition.CLOSED)
    assert updated.position is SwitchPosition.CLOSED
    report = validate_substation_topology(network)
    assert report.structurally_valid is False
    assert any(item.code == "ES001-BAY-BUSBAR-SELECTION" for item in report.diagnostics)
    assert any(len(item.connected_busbar_names) == 2 for item in report.interfaces)

    restored = SetSwitchPosition().execute(network, switch.id, SwitchPosition.OPEN)
    assert restored.position is SwitchPosition.OPEN
    assert validate_substation_topology(network).structurally_valid is True


def test_pfa_es001_json_round_trip_preserves_switches_interfaces_and_symbol_pin_maps(
    tmp_path: Path,
) -> None:
    workspace = BuildPFAES001Substation().execute().workspace
    repository = JSONNetworkDocumentRepository()
    path = repository.save(workspace, tmp_path / "pfa-es-001.network.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    loaded = repository.load(path)

    assert payload["schema_version"] == "1.6"
    assert len(loaded.network.buses) == 8
    assert len(loaded.network.equipment) == 10
    assert len(loaded.diagram_symbols) == 10
    assert {bus.name: bus.kind for bus in loaded.network.buses} == {
        bus.name: bus.kind for bus in workspace.network.buses
    }
    loaded_switches = {
        item.name: item.position
        for item in loaded.network.equipment
        if isinstance(item, SwitchingDevice)
    }
    source_switches = {
        item.name: item.position
        for item in workspace.network.equipment
        if isinstance(item, SwitchingDevice)
    }
    assert loaded_switches == source_switches
    assert all(
        item.terminal_mappings and item.equipment_id is not None
        for item in loaded.diagram_symbols.values()
    )
    assert (
        sum(isinstance(item, UnresolvedEquipmentInterface) for item in loaded.network.equipment)
        == 2
    )


def test_network_document_writer_uses_schema_1_6_and_keeps_schema_1_0_readable(
    tmp_path: Path,
) -> None:
    workspace = BuildPFAES001Substation().execute().workspace
    path = JSONNetworkDocumentRepository().save(workspace, tmp_path / "substation.pfan")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "1.6"

    payload["schema_version"] = "1.0"
    for bus in payload["network"]["buses"]:
        bus.pop("kind", None)
    path.write_text(json.dumps(payload), encoding="utf-8")
    legacy = JSONNetworkDocumentRepository().load(path)
    assert all(bus.kind is BusKind.BUSBAR for bus in legacy.network.buses)


def test_network_document_round_trip_preserves_concrete_two_winding_transformer(
    tmp_path: Path,
) -> None:
    from uuid import uuid4

    from power_fault_analyzer.application.use_cases.network_workspace import NetworkWorkspace
    from power_fault_analyzer.domain.aggregates.network import Network
    from power_fault_analyzer.domain.entities.bus import Bus
    from power_fault_analyzer.domain.entities.terminal import Terminal
    from power_fault_analyzer.domain.enums.grounding_mode import GroundingMode
    from power_fault_analyzer.domain.enums.winding_connection import WindingConnection
    from power_fault_analyzer.domain.enums.winding_designation import WindingDesignation
    from power_fault_analyzer.domain.value_objects.electrical_impedance_base import (
        ElectricalImpedanceBase,
    )
    from power_fault_analyzer.domain.value_objects.frequency import Frequency
    from power_fault_analyzer.domain.value_objects.neutral_grounding import NeutralGrounding
    from power_fault_analyzer.domain.value_objects.per_unit_impedance import (
        PerUnitImpedance,
        SequencePerUnitImpedance,
    )
    from power_fault_analyzer.domain.value_objects.tap_changer import TapChanger
    from power_fault_analyzer.domain.value_objects.transformer_winding import TransformerWinding
    from power_fault_analyzer.domain.value_objects.vector_group import VectorGroup
    from power_fault_analyzer.domain.value_objects.voltage import Voltage
    from power_fault_analyzer.equipment.transformers.two_winding_transformer import (
        TwoWindingTransformer,
    )

    network = Network("Transformer persistence")
    hv_bus = Bus("HV", Voltage.from_kv(220.0))
    lv_bus = Bus("LV", Voltage.from_kv(33.0))
    network.add_bus(hv_bus)
    network.add_bus(lv_bus)
    equipment_id = uuid4()
    terminals = (
        Terminal(equipment_id, "HV", hv_bus.nominal_voltage),
        Terminal(equipment_id, "LV", lv_bus.nominal_voltage),
    )
    windings = (
        TransformerWinding(
            WindingDesignation.HIGH_VOLTAGE,
            220.0,
            100.0,
            WindingConnection.STAR,
            NeutralGrounding.solid(),
            neutral_terminal_available=True,
            tap_changer=TapChanger(-8, 8, 0, 2, 1.25),
        ),
        TransformerWinding(
            WindingDesignation.LOW_VOLTAGE,
            33.0,
            100.0,
            WindingConnection.DELTA,
            None,
        ),
    )
    transformer = TwoWindingTransformer(
        id=equipment_id,
        name="TR-220/33-01",
        terminals=terminals,
        windings=windings,
        frequency=Frequency(60.0),
        vector_group=VectorGroup(WindingConnection.STAR, WindingConnection.DELTA, 11),
        sequence_impedances=SequencePerUnitImpedance(
            ElectricalImpedanceBase(100.0, 220.0),
            PerUnitImpedance(0.01, 0.12),
            PerUnitImpedance(0.012, 0.13),
            PerUnitImpedance(0.02, 0.1),
        ),
    )
    network.add_equipment(transformer)
    network.connect(terminals[0].id, hv_bus.id)
    network.connect(terminals[1].id, lv_bus.id)
    workspace = NetworkWorkspace(network)

    repository = JSONNetworkDocumentRepository()
    path = repository.save(workspace, tmp_path / "transformer.network.json")
    loaded = repository.load(path)
    restored = loaded.network.get_equipment(equipment_id)

    assert isinstance(restored, TwoWindingTransformer)
    assert restored.vector_group_notation == "YNd11"
    assert restored.windings[0].tap_changer == windings[0].tap_changer
    assert restored.windings[0].neutral_grounding.mode is GroundingMode.SOLID
    assert restored.sequence_impedances.positive.value_pu == pytest.approx(0.01 + 0.12j)
    assert restored.sequence_impedances.zero.value_pu == pytest.approx(0.02 + 0.1j)
