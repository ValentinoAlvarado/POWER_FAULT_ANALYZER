"""Analytical tests for line-interior short-circuit calculations."""

from __future__ import annotations

from uuid import uuid4

import pytest

from power_fault_analyzer.domain.enums.fault_type import FaultType
from power_fault_analyzer.domain.enums.sequence_type import SequenceType
from power_fault_analyzer.domain.value_objects.diagnostic import (
    DiagnosticSeverity,
    DomainDiagnostic,
)
from power_fault_analyzer.domain.value_objects.electrical_impedance_base import (
    ElectricalImpedanceBase,
)
from power_fault_analyzer.domain.value_objects.line_fault_specification import (
    LineFaultSpecification,
)
from power_fault_analyzer.infrastructure.numerical.line_fault import (
    LineFaultCalculationError,
    LineFaultSolver,
    NonFaultableBranchError,
    UnknownLineFaultBranchError,
)
from power_fault_analyzer.network.sequence_networks.models import (
    SequenceBranch,
    SequenceNetwork,
    SequenceNetworkSet,
    SequenceNode,
    SequenceShunt,
    SystemBaseSet,
)


@pytest.fixture
def line_study():
    bus_from = uuid4()
    bus_to = uuid4()
    network_id = uuid4()
    line_id = uuid4()
    impedances = {
        SequenceType.POSITIVE: 0.20 + 0.50j,
        SequenceType.NEGATIVE: 0.24 + 0.56j,
        SequenceType.ZERO: 0.60 + 1.40j,
    }
    source_from = {
        SequenceType.POSITIVE: 0.05 + 0.20j,
        SequenceType.NEGATIVE: 0.06 + 0.22j,
        SequenceType.ZERO: 0.12 + 0.42j,
    }
    source_to = {
        SequenceType.POSITIVE: 0.07 + 0.22j,
        SequenceType.NEGATIVE: 0.08 + 0.24j,
        SequenceType.ZERO: 0.15 + 0.45j,
    }
    models = {}
    for sequence in (
        SequenceType.POSITIVE,
        SequenceType.NEGATIVE,
        SequenceType.ZERO,
    ):
        emf = 1.0 + 0.0j if sequence is SequenceType.POSITIVE else 0.0j
        models[sequence] = SequenceNetwork(
            network_id=network_id,
            sequence=sequence,
            nodes=(SequenceNode(bus_from, "BUS-FROM"), SequenceNode(bus_to, "BUS-TO")),
            branches=(
                SequenceBranch(
                    id=line_id,
                    name="LINE-FROM-TO",
                    from_node_id=bus_from,
                    to_node_id=bus_to,
                    series_impedance_pu=impedances[sequence],
                    length_km=10.0,
                ),
            ),
            shunts=(
                SequenceShunt(
                    id=uuid4(),
                    name=f"SOURCE-FROM-{sequence.value}",
                    node_id=bus_from,
                    admittance_pu=1.0 / source_from[sequence],
                    source_voltage_pu=emf,
                ),
                SequenceShunt(
                    id=uuid4(),
                    name=f"SOURCE-TO-{sequence.value}",
                    node_id=bus_to,
                    admittance_pu=1.0 / source_to[sequence],
                    source_voltage_pu=emf,
                ),
            ),
        )
    return (
        bus_from,
        bus_to,
        line_id,
        impedances,
        source_from,
        source_to,
        SequenceNetworkSet(
            positive=models[SequenceType.POSITIVE],
            negative=models[SequenceType.NEGATIVE],
            zero=models[SequenceType.ZERO],
        ),
        SystemBaseSet(100.0, {bus_from: 13.8, bus_to: 13.8}),
    )


def test_three_phase_line_fault_splits_impedance_and_reports_both_terminal_currents(
    line_study,
):
    (
        bus_from,
        bus_to,
        line_id,
        impedances,
        source_from,
        source_to,
        networks,
        system_base,
    ) = line_study
    location = 0.4
    result = LineFaultSolver().solve(
        networks,
        LineFaultSpecification(FaultType.THREE_PHASE, line_id, location),
        system_base,
    )

    expected_from = 1.0 / (
        source_from[SequenceType.POSITIVE] + location * impedances[SequenceType.POSITIVE]
    )
    expected_to = 1.0 / (
        source_to[SequenceType.POSITIVE] + (1.0 - location) * impedances[SequenceType.POSITIVE]
    )
    expected_fault = expected_from + expected_to
    assert result.fault_result.sequence_currents_pu[SequenceType.POSITIVE] == pytest.approx(
        expected_fault
    )
    assert result.from_terminal.sequence_currents_into_line_pu[
        SequenceType.POSITIVE
    ] == pytest.approx(expected_from)
    assert result.to_terminal.sequence_currents_into_line_pu[
        SequenceType.POSITIVE
    ] == pytest.approx(expected_to)
    assert result.from_terminal.bus_id == bus_from
    assert result.to_terminal.bus_id == bus_to
    assert result.distance_from_km == pytest.approx(4.0)
    assert result.distance_to_km == pytest.approx(6.0)
    assert result.fault_result.bus_id == result.fault_node_id
    assert networks.positive.branches[0].id == line_id
    assert len(networks.positive.branches) == 1


def test_single_line_ground_fault_returns_sequence_and_phase_states(line_study):
    _, _, line_id, _, _, _, networks, system_base = line_study
    result = LineFaultSolver().solve(
        networks,
        LineFaultSpecification(FaultType.SINGLE_LINE_TO_GROUND, line_id, 0.25),
        system_base,
    )

    assert result.fault_result.phase_currents_pu[1] == pytest.approx(0.0j, abs=1e-10)
    assert result.fault_result.phase_currents_pu[2] == pytest.approx(0.0j, abs=1e-10)
    assert result.from_terminal.phase_voltages_kv[0] != 0.0j
    assert set(result.from_terminal.sequence_voltages_pu) == set(SequenceType)
    assert set(result.to_terminal.sequence_currents_into_line_pu) == set(SequenceType)


def test_line_to_line_fault_does_not_require_zero_sequence(line_study):
    _, _, line_id, _, _, _, networks, system_base = line_study
    result = LineFaultSolver().solve(
        networks,
        LineFaultSpecification(FaultType.LINE_TO_LINE, line_id, 0.75),
        system_base,
    )

    assert result.fault_result.sequence_currents_pu[SequenceType.ZERO] == 0.0j
    assert result.fault_result.phase_currents_pu[0] == pytest.approx(0.0j, abs=1e-10)
    assert result.from_terminal.sequence_currents_into_line_pu[SequenceType.ZERO] == 0.0j


def test_double_line_ground_fault_preserves_phase_boundary_conditions(line_study):
    _, _, line_id, _, _, _, networks, system_base = line_study
    result = LineFaultSolver().solve(
        networks,
        LineFaultSpecification(FaultType.DOUBLE_LINE_TO_GROUND, line_id, 0.5, 0.02 + 0.03j),
        system_base,
    )
    ia, ib, ic = result.fault_result.phase_currents_pu
    _, vb, vc = result.fault_result.phase_voltages_pu
    assert ia == pytest.approx(0.0j, abs=1e-10)
    assert vb == pytest.approx(vc, abs=1e-10)
    assert result.fault_result.ground_current_pu == pytest.approx(ib + ic)


def test_fault_impedance_can_be_converted_from_ohms(line_study):
    _, _, line_id, _, _, _, _, _ = line_study
    base = ElectricalImpedanceBase(100.0, 13.8)
    fault = LineFaultSpecification.from_ohms(
        FaultType.THREE_PHASE,
        line_id,
        0.5,
        0.5 + 1.0j,
        base,
    )
    assert fault.fault_impedance_pu == pytest.approx((0.5 + 1.0j) / base.base_impedance_ohm)


@pytest.mark.parametrize("fraction", [0.0, 1.0, -0.1, 1.1, float("nan"), float("inf")])
def test_line_fault_rejects_invalid_location_fraction(line_study, fraction):
    _, _, line_id, _, _, _, _, _ = line_study
    with pytest.raises((TypeError, ValueError)):
        LineFaultSpecification(FaultType.THREE_PHASE, line_id, fraction)


def test_unknown_line_id_is_rejected(line_study):
    _, _, _, _, _, _, networks, system_base = line_study
    with pytest.raises(UnknownLineFaultBranchError):
        LineFaultSolver().solve(
            networks,
            LineFaultSpecification(FaultType.THREE_PHASE, uuid4(), 0.5),
            system_base,
        )


def test_lumped_branch_without_physical_length_is_not_faultable(line_study):
    _, _, line_id, _, _, _, networks, system_base = line_study
    from power_fault_analyzer.network.sequence_networks.models import SequenceBranch

    def replace_branch(network):
        original = network.branches[0]
        branch = SequenceBranch(
            id=original.id,
            name=original.name,
            from_node_id=original.from_node_id,
            to_node_id=original.to_node_id,
            series_impedance_pu=original.series_impedance_pu,
        )
        return SequenceNetwork(
            network_id=network.network_id,
            sequence=network.sequence,
            nodes=network.nodes,
            branches=(branch,),
            shunts=network.shunts,
            reference_node_id=network.reference_node_id,
        )

    reduced = SequenceNetworkSet(
        positive=replace_branch(networks.positive),
        negative=replace_branch(networks.negative),
        zero=replace_branch(networks.zero),
    )
    with pytest.raises(NonFaultableBranchError):
        LineFaultSolver().solve(
            reduced,
            LineFaultSpecification(FaultType.THREE_PHASE, line_id, 0.5),
            system_base,
        )


def test_three_phase_line_fault_does_not_require_zero_sequence_line_model(line_study):
    _, _, line_id, _, _, _, networks, system_base = line_study
    incomplete_zero = SequenceNetwork(
        network_id=networks.zero.network_id,
        sequence=SequenceType.ZERO,
        nodes=networks.zero.nodes,
        branches=(),
        shunts=(),
        diagnostics=(
            DomainDiagnostic(
                code="TEST-ZERO-INCOMPLETE",
                message="Zero-sequence line model intentionally unavailable.",
                severity=DiagnosticSeverity.ERROR,
            ),
        ),
    )
    reduced = SequenceNetworkSet(networks.positive, networks.negative, incomplete_zero)

    result = LineFaultSolver().solve(
        reduced,
        LineFaultSpecification(FaultType.THREE_PHASE, line_id, 0.5),
        system_base,
    )

    assert result.fault_result.sequence_currents_pu[SequenceType.POSITIVE] != 0.0j


def test_split_line_retains_pi_shunts_at_physical_terminals(line_study):
    _, _, line_id, _, _, _, networks, _ = line_study
    original = networks.positive.branches[0]
    branch_with_shunts = SequenceBranch(
        id=original.id,
        name=original.name,
        from_node_id=original.from_node_id,
        to_node_id=original.to_node_id,
        series_impedance_pu=original.series_impedance_pu,
        shunt_admittance_from_pu=0.003 + 0.01j,
        shunt_admittance_to_pu=0.004 + 0.012j,
        length_km=original.length_km,
    )
    network_with_shunts = SequenceNetwork(
        network_id=networks.positive.network_id,
        sequence=SequenceType.POSITIVE,
        nodes=networks.positive.nodes,
        branches=(branch_with_shunts,),
        shunts=networks.positive.shunts,
        reference_node_id=networks.positive.reference_node_id,
    )
    split = LineFaultSolver()._split_network(
        network_with_shunts,
        LineFaultSpecification(FaultType.THREE_PHASE, line_id, 0.3),
    )
    assert split.left_branch.shunt_admittance_from_pu == pytest.approx(0.003 + 0.01j)
    assert split.left_branch.shunt_admittance_to_pu == 0.0j
    assert split.right_branch.shunt_admittance_from_pu == 0.0j
    assert split.right_branch.shunt_admittance_to_pu == pytest.approx(0.004 + 0.012j)
    assert (
        split.left_branch.series_impedance_pu + split.right_branch.series_impedance_pu
    ) == pytest.approx(split.original_branch.series_impedance_pu)


def test_line_fault_rejects_inconsistent_sequence_branch_lengths(line_study):
    _, _, line_id, _, _, _, networks, system_base = line_study
    original = networks.negative.branches[0]
    inconsistent_branch = SequenceBranch(
        id=original.id,
        name=original.name,
        from_node_id=original.from_node_id,
        to_node_id=original.to_node_id,
        series_impedance_pu=original.series_impedance_pu,
        length_km=12.0,
    )
    inconsistent_negative = SequenceNetwork(
        network_id=networks.negative.network_id,
        sequence=SequenceType.NEGATIVE,
        nodes=networks.negative.nodes,
        branches=(inconsistent_branch,),
        shunts=networks.negative.shunts,
        reference_node_id=networks.negative.reference_node_id,
    )
    inconsistent_set = SequenceNetworkSet(
        positive=networks.positive,
        negative=inconsistent_negative,
        zero=networks.zero,
    )

    with pytest.raises(
        LineFaultCalculationError,
        match="inconsistent terminal topology or physical length",
    ):
        LineFaultSolver().solve(
            inconsistent_set,
            LineFaultSpecification(FaultType.LINE_TO_LINE, line_id, 0.5),
            system_base,
        )
