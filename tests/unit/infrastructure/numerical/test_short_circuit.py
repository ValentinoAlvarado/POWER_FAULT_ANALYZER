"""Analytical tests for bus short-circuit boundary conditions."""

from __future__ import annotations

import math
from uuid import uuid4

import numpy as np
import pytest

from power_fault_analyzer.domain.enums.fault_type import FaultType
from power_fault_analyzer.domain.enums.sequence_type import SequenceType
from power_fault_analyzer.domain.value_objects.diagnostic import (
    DiagnosticSeverity,
    DomainDiagnostic,
)
from power_fault_analyzer.domain.value_objects.fault_specification import (
    FaultSpecification,
)
from power_fault_analyzer.infrastructure.numerical.short_circuit import (
    NonlinearSourceCalculationRequiredError,
    ShortCircuitSolver,
    SparseTheveninCalculator,
    UnknownFaultBusError,
)
from power_fault_analyzer.infrastructure.numerical.ybus import (
    IncompleteSequenceNetworkError,
    SingularAdmittanceMatrixError,
    SparseYBusAssembler,
)
from power_fault_analyzer.network.sequence_networks.models import (
    SequenceNetwork,
    SequenceNetworkSet,
    SequenceNode,
    SequenceShunt,
    SystemBaseSet,
)


@pytest.fixture
def study():
    bus_id = uuid4()
    network_id = uuid4()
    impedances = {
        SequenceType.ZERO: 0.18 + 0.52j,
        SequenceType.POSITIVE: 0.08 + 0.24j,
        SequenceType.NEGATIVE: 0.11 + 0.31j,
    }
    source_voltage = 1.02 + 0.025j
    models = {}
    for sequence, impedance in impedances.items():
        node = SequenceNode(bus_id, "BUS-FAULT")
        source_emf = source_voltage if sequence is SequenceType.POSITIVE else 0.0j
        shunt = SequenceShunt(
            id=uuid4(),
            name=f"SOURCE-{sequence.value}",
            node_id=bus_id,
            admittance_pu=1.0 / impedance,
            source_voltage_pu=source_emf,
        )
        models[sequence] = SequenceNetwork(
            network_id=network_id,
            sequence=sequence,
            nodes=(node,),
            branches=(),
            shunts=(shunt,),
        )
    network_set = SequenceNetworkSet(
        positive=models[SequenceType.POSITIVE],
        negative=models[SequenceType.NEGATIVE],
        zero=models[SequenceType.ZERO],
    )
    system_base = SystemBaseSet(
        base_power_mva=100.0,
        bus_voltage_bases_kv={bus_id: 13.8},
    )
    return bus_id, impedances, source_voltage, network_set, system_base


def test_sparse_thevenin_calculator_returns_open_circuit_voltage_and_zth(study):
    bus_id, impedances, source_voltage, networks, _ = study
    ybus = SparseYBusAssembler().assemble(networks.positive)

    equivalent = SparseTheveninCalculator().calculate(ybus, bus_id)

    assert equivalent.sequence is SequenceType.POSITIVE
    assert equivalent.bus_id == bus_id
    assert equivalent.prefault_voltage_pu == pytest.approx(source_voltage)
    assert equivalent.driving_point_impedance_pu == pytest.approx(impedances[SequenceType.POSITIVE])


def test_sparse_thevenin_ignores_an_unrelated_floating_sequence_island(study):
    bus_id, impedances, source_voltage, networks, _ = study
    floating_bus_id = uuid4()
    positive = networks.positive
    network_with_unrelated_island = SequenceNetwork(
        network_id=positive.network_id,
        sequence=positive.sequence,
        nodes=(*positive.nodes, SequenceNode(floating_bus_id, "UNRELATED-FLOATING")),
        branches=positive.branches,
        shunts=positive.shunts,
        diagnostics=positive.diagnostics,
    )
    ybus = SparseYBusAssembler().assemble(network_with_unrelated_island)

    equivalent = SparseTheveninCalculator().calculate(ybus, bus_id)

    assert equivalent.prefault_voltage_pu == pytest.approx(source_voltage)
    assert equivalent.driving_point_impedance_pu == pytest.approx(impedances[SequenceType.POSITIVE])


def test_three_phase_fault_matches_positive_sequence_thevenin_solution(study):
    bus_id, impedances, source_voltage, networks, system_base = study
    fault_impedance = 0.025 + 0.07j
    fault = FaultSpecification(FaultType.THREE_PHASE, bus_id, fault_impedance)

    result = ShortCircuitSolver().solve(networks, fault, system_base)

    expected = source_voltage / (impedances[SequenceType.POSITIVE] + fault_impedance)
    assert result.fault_impedance_pu == pytest.approx(fault_impedance)
    assert result.sequence_currents_pu[SequenceType.POSITIVE] == pytest.approx(expected)
    assert result.sequence_currents_pu[SequenceType.NEGATIVE] == 0.0j
    assert result.sequence_currents_pu[SequenceType.ZERO] == 0.0j
    assert result.phase_currents_pu[0] == pytest.approx(expected)
    assert result.phase_currents_pu[1] == pytest.approx(expected * np.exp(-2j * np.pi / 3))
    assert result.phase_currents_pu[2] == pytest.approx(expected * np.exp(2j * np.pi / 3))
    assert max(abs(value) for value in result.phase_voltages_pu) > 0.0
    assert result.maximum_phase_current_ka == pytest.approx(
        abs(expected) * system_base.for_bus(bus_id).base_current_ka
    )


def test_single_line_to_ground_fault_has_equal_sequence_currents(study):
    bus_id, impedances, source_voltage, networks, _ = study
    fault_impedance = 0.03 + 0.04j
    fault = FaultSpecification(FaultType.SINGLE_LINE_TO_GROUND, bus_id, fault_impedance)

    result = ShortCircuitSolver().solve(networks, fault, study[4])

    expected = source_voltage / (
        impedances[SequenceType.ZERO]
        + impedances[SequenceType.POSITIVE]
        + impedances[SequenceType.NEGATIVE]
        + 3.0 * fault_impedance
    )
    for sequence in (SequenceType.ZERO, SequenceType.POSITIVE, SequenceType.NEGATIVE):
        assert result.sequence_currents_pu[sequence] == pytest.approx(expected)
    assert result.phase_currents_pu[0] == pytest.approx(3.0 * expected)
    assert result.phase_currents_pu[1] == pytest.approx(0.0j, abs=1e-12)
    assert result.phase_currents_pu[2] == pytest.approx(0.0j, abs=1e-12)
    assert result.ground_current_pu == pytest.approx(3.0 * expected)
    assert result.phase_voltages_pu[0] == pytest.approx(fault_impedance * 3.0 * expected)


def test_line_to_line_fault_has_no_zero_sequence_and_opposite_bc_currents(study):
    bus_id, impedances, source_voltage, networks, system_base = study
    fault_impedance = 0.02 + 0.06j
    fault = FaultSpecification(FaultType.LINE_TO_LINE, bus_id, fault_impedance)

    result = ShortCircuitSolver().solve(networks, fault, system_base)

    expected = source_voltage / (
        impedances[SequenceType.POSITIVE] + impedances[SequenceType.NEGATIVE] + fault_impedance
    )
    assert result.sequence_currents_pu[SequenceType.POSITIVE] == pytest.approx(expected)
    assert result.sequence_currents_pu[SequenceType.NEGATIVE] == pytest.approx(-expected)
    assert result.sequence_currents_pu[SequenceType.ZERO] == 0.0j
    assert result.phase_currents_pu[0] == pytest.approx(0.0j, abs=1e-12)
    assert result.phase_currents_pu[1] == pytest.approx(-result.phase_currents_pu[2])
    assert result.phase_voltages_pu[1] - result.phase_voltages_pu[2] == pytest.approx(
        fault_impedance * result.phase_currents_pu[1]
    )
    assert result.ground_current_pu == 0.0j
    assert result.base_current_ka == pytest.approx(100.0 / (math.sqrt(3.0) * 13.8))


def test_double_line_to_ground_fault_obeys_bc_ground_boundary_conditions(study):
    bus_id, impedances, source_voltage, networks, system_base = study
    fault_impedance = 0.015 + 0.055j
    fault = FaultSpecification(FaultType.DOUBLE_LINE_TO_GROUND, bus_id, fault_impedance)

    result = ShortCircuitSolver().solve(networks, fault, system_base)

    ia, ib, ic = result.phase_currents_pu
    _va, vb, vc = result.phase_voltages_pu
    assert ia == pytest.approx(0.0j, abs=1e-11)
    assert vb == pytest.approx(vc, abs=1e-11)
    assert vb == pytest.approx(fault_impedance * (ib + ic))
    assert result.ground_current_pu == pytest.approx(ib + ic)

    z0 = impedances[SequenceType.ZERO]
    z1 = impedances[SequenceType.POSITIVE]
    z2 = impedances[SequenceType.NEGATIVE]
    denominator = z2 + z0 + 3.0 * fault_impedance
    expected_i1 = source_voltage / (z1 + z2 * (z0 + 3.0 * fault_impedance) / denominator)
    assert result.sequence_currents_pu[SequenceType.POSITIVE] == pytest.approx(expected_i1)
    assert result.sequence_currents_pu[SequenceType.NEGATIVE] == pytest.approx(
        -expected_i1 * (z0 + 3.0 * fault_impedance) / denominator
    )
    assert result.sequence_currents_pu[SequenceType.ZERO] == pytest.approx(
        -expected_i1 * z2 / denominator
    )


def test_fault_impedance_can_be_converted_from_ohms(study):
    bus_id, _, _, _, system_base = study
    base = system_base.for_bus(bus_id)

    fault = FaultSpecification.from_ohms(
        FaultType.SINGLE_LINE_TO_GROUND,
        bus_id,
        0.5 + 1.0j,
        base,
    )

    assert fault.fault_impedance_pu == pytest.approx((0.5 + 1.0j) / base.base_impedance_ohm)


def test_three_phase_fault_does_not_require_zero_sequence_network_completeness(study):
    bus_id, _, _, networks, system_base = study
    incomplete_zero = SequenceNetwork(
        network_id=networks.zero.network_id,
        sequence=SequenceType.ZERO,
        nodes=networks.zero.nodes,
        branches=(),
        shunts=(),
        diagnostics=(
            DomainDiagnostic(
                code="TEST-ZERO-INCOMPLETE",
                message="Intentionally incomplete for this test.",
                severity=DiagnosticSeverity.ERROR,
            ),
        ),
    )
    reduced = SequenceNetworkSet(networks.positive, networks.negative, incomplete_zero)

    result = ShortCircuitSolver().solve(
        reduced,
        FaultSpecification(FaultType.THREE_PHASE, bus_id),
        system_base,
    )

    assert result.sequence_currents_pu[SequenceType.POSITIVE] != 0.0j


def test_single_line_ground_fault_rejects_incomplete_zero_sequence(study):
    bus_id, _, _, networks, system_base = study
    incomplete_zero = SequenceNetwork(
        network_id=networks.zero.network_id,
        sequence=SequenceType.ZERO,
        nodes=networks.zero.nodes,
        branches=(),
        shunts=(),
        diagnostics=(
            DomainDiagnostic(
                code="TEST-ZERO-INCOMPLETE",
                message="Intentionally incomplete for this test.",
                severity=DiagnosticSeverity.ERROR,
            ),
        ),
    )
    reduced = SequenceNetworkSet(networks.positive, networks.negative, incomplete_zero)

    with pytest.raises(IncompleteSequenceNetworkError):
        ShortCircuitSolver().solve(
            reduced,
            FaultSpecification(FaultType.SINGLE_LINE_TO_GROUND, bus_id),
            system_base,
        )


def test_converter_source_requires_nonlinear_fault_solver(study):
    bus_id, _, _, networks, system_base = study
    nonlinear_positive = SequenceNetwork(
        network_id=networks.positive.network_id,
        sequence=SequenceType.POSITIVE,
        nodes=networks.positive.nodes,
        branches=networks.positive.branches,
        shunts=networks.positive.shunts,
        nonlinear_source_ids=(uuid4(),),
    )
    reduced = SequenceNetworkSet(nonlinear_positive, networks.negative, networks.zero)

    with pytest.raises(NonlinearSourceCalculationRequiredError):
        ShortCircuitSolver().solve(
            reduced,
            FaultSpecification(FaultType.THREE_PHASE, bus_id),
            system_base,
        )


def test_fault_bus_must_exist_in_system_base_and_sequence_network(study):
    _, _, _, networks, system_base = study
    unknown_bus = uuid4()
    fault = FaultSpecification(FaultType.THREE_PHASE, unknown_bus)

    with pytest.raises(UnknownFaultBusError):
        ShortCircuitSolver().solve(networks, fault, system_base)


def test_singular_fault_boundary_equation_is_reported(study):
    bus_id, _, _, networks, system_base = study
    zero_source = SequenceNetwork(
        network_id=networks.positive.network_id,
        sequence=SequenceType.POSITIVE,
        nodes=networks.positive.nodes,
        branches=(),
        shunts=(),
    )
    reduced = SequenceNetworkSet(zero_source, networks.negative, networks.zero)

    with pytest.raises(SingularAdmittanceMatrixError):
        ShortCircuitSolver().solve(
            reduced,
            FaultSpecification(FaultType.THREE_PHASE, bus_id),
            system_base,
        )


def test_fault_specification_rejects_negative_resistance(study):
    bus_id = study[0]
    with pytest.raises(ValueError, match="resistance"):
        FaultSpecification(FaultType.THREE_PHASE, bus_id, -0.1 + 0.2j)


def test_short_circuit_result_exposes_read_only_sequence_mappings(study):
    bus_id, _, _, networks, system_base = study
    result = ShortCircuitSolver().solve(
        networks,
        FaultSpecification(FaultType.THREE_PHASE, bus_id),
        system_base,
    )

    with pytest.raises(TypeError):
        result.sequence_currents_pu[SequenceType.POSITIVE] = 0.0j


def test_double_line_to_ground_boundary_equations_have_finite_solution(study):
    bus_id, _, _, networks, system_base = study
    result = ShortCircuitSolver().solve(
        networks,
        FaultSpecification(FaultType.DOUBLE_LINE_TO_GROUND, bus_id, 0.01 + 0.08j),
        system_base,
    )

    for value in result.sequence_currents_pu.values():
        assert np.isfinite(value.real)
        assert np.isfinite(value.imag)


def test_short_circuit_solver_applies_explicit_converter_phasor_to_fault_study():
    from power_fault_analyzer.domain.value_objects.converter_current_command import (
        ConverterSequenceCurrentCommand,
    )
    from power_fault_analyzer.domain.value_objects.electrical_impedance_base import (
        ElectricalImpedanceBase,
    )
    from power_fault_analyzer.domain.value_objects.source_models import (
        ConverterFaultCurrentCapability,
    )

    bus_id = uuid4()
    source_id = uuid4()
    network_id = uuid4()
    base = ElectricalImpedanceBase(100.0, 13.8)
    capability = ConverterFaultCurrentCapability(
        base,
        overall_current_limit_pu=1.5,
        positive_sequence_limit_pu=1.2,
        negative_sequence_limit_pu=0.2,
        zero_sequence_limit_pu=0.1,
    )
    source_impedances = {
        SequenceType.POSITIVE: 0.1 + 0.2j,
        SequenceType.NEGATIVE: 0.1 + 0.3j,
        SequenceType.ZERO: 0.2 + 0.4j,
    }
    sequence_models = {}
    for sequence, impedance in source_impedances.items():
        sequence_models[sequence] = SequenceNetwork(
            network_id=network_id,
            sequence=sequence,
            nodes=(SequenceNode(bus_id, "CONVERTER-BUS"),),
            branches=(),
            shunts=(
                SequenceShunt(
                    uuid4(),
                    f"GRID-{sequence.value}",
                    bus_id,
                    1.0 / impedance,
                    1.0 + 0j if sequence is SequenceType.POSITIVE else 0j,
                ),
            ),
            nonlinear_source_ids=(source_id,),
            converter_capabilities={source_id: capability},
            converter_bus_ids={source_id: bus_id},
        )
    networks = SequenceNetworkSet(
        positive=sequence_models[SequenceType.POSITIVE],
        negative=sequence_models[SequenceType.NEGATIVE],
        zero=sequence_models[SequenceType.ZERO],
    )
    system_base = SystemBaseSet(100.0, {bus_id: 13.8})
    command_currents = {
        SequenceType.POSITIVE: 0.2 + 0.1j,
        SequenceType.NEGATIVE: 0.0j,
        SequenceType.ZERO: 0.0j,
    }
    command = ConverterSequenceCurrentCommand(
        source_id,
        bus_id,
        capability,
        command_currents,
    )
    fault_impedance = 0.05 + 0.02j
    fault = FaultSpecification(FaultType.THREE_PHASE, bus_id, fault_impedance)

    with pytest.raises(NonlinearSourceCalculationRequiredError):
        ShortCircuitSolver().solve(networks, fault, system_base)

    result = ShortCircuitSolver().solve(
        networks,
        fault,
        system_base,
        converter_current_commands=(command,),
    )

    impedance = source_impedances[SequenceType.POSITIVE]
    expected_prefault_voltage = 1.0 + impedance * command_currents[SequenceType.POSITIVE]
    expected_fault_current = expected_prefault_voltage / (impedance + fault_impedance)
    assert result.prefault_sequence_voltages_pu[SequenceType.POSITIVE] == pytest.approx(
        expected_prefault_voltage
    )
    assert result.sequence_currents_pu[SequenceType.POSITIVE] == pytest.approx(
        expected_fault_current
    )
    assert any(
        diagnostic.code == "SC-CONVERTER-FIXED-PHASOR-ASSUMPTION"
        for diagnostic in result.diagnostics
    )

    incompatible_command = ConverterSequenceCurrentCommand(
        source_id,
        bus_id,
        capability,
        {
            SequenceType.POSITIVE: 0.2 + 0.0j,
            SequenceType.NEGATIVE: 0.05 + 0.0j,
            SequenceType.ZERO: 0.0j,
        },
    )
    with pytest.raises(NonlinearSourceCalculationRequiredError, match="would otherwise be ignored"):
        ShortCircuitSolver().solve(
            networks,
            fault,
            system_base,
            converter_current_commands=(incompatible_command,),
        )


def test_short_circuit_solver_rejects_converter_command_for_unregistered_bus():
    from power_fault_analyzer.domain.value_objects.converter_current_command import (
        ConverterSequenceCurrentCommand,
    )
    from power_fault_analyzer.domain.value_objects.electrical_impedance_base import (
        ElectricalImpedanceBase,
    )
    from power_fault_analyzer.domain.value_objects.source_models import (
        ConverterFaultCurrentCapability,
    )

    bus_id = uuid4()
    other_bus_id = uuid4()
    source_id = uuid4()
    network_id = uuid4()
    base = ElectricalImpedanceBase(100.0, 13.8)
    capability = ConverterFaultCurrentCapability(base, 1.2, 1.0, 0.2, 0.1)
    models = {}
    for sequence in SequenceType:
        models[sequence] = SequenceNetwork(
            network_id,
            sequence,
            (SequenceNode(bus_id, "BUS"),),
            (),
            (SequenceShunt(uuid4(), "GRID", bus_id, 5.0 + 0j, 1.0 + 0j),),
            nonlinear_source_ids=(source_id,),
            converter_capabilities={source_id: capability},
            converter_bus_ids={source_id: bus_id},
        )
    networks = SequenceNetworkSet(
        models[SequenceType.POSITIVE],
        models[SequenceType.NEGATIVE],
        models[SequenceType.ZERO],
    )
    command = ConverterSequenceCurrentCommand(
        source_id,
        other_bus_id,
        capability,
        {sequence: 0.0j for sequence in SequenceType},
    )
    system_base = SystemBaseSet(100.0, {bus_id: 13.8, other_bus_id: 13.8})

    with pytest.raises(NonlinearSourceCalculationRequiredError, match="registered connection"):
        ShortCircuitSolver().solve(
            networks,
            FaultSpecification(FaultType.THREE_PHASE, bus_id),
            system_base,
            converter_current_commands=(command,),
        )
