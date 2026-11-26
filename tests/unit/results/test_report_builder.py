from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from power_fault_analyzer.domain.enums.fault_type import FaultType
from power_fault_analyzer.domain.enums.iec60909 import IEC60909CurrentCase
from power_fault_analyzer.domain.enums.sequence_type import SequenceType
from power_fault_analyzer.domain.value_objects.iec60909_study import IEC60909StudyResult
from power_fault_analyzer.domain.value_objects.line_fault_result import (
    LineFaultStudyResult,
    LineTerminalState,
)
from power_fault_analyzer.domain.value_objects.short_circuit_result import ShortCircuitResult
from power_fault_analyzer.infrastructure.numerical.iec60909_source_contributions import (
    IEC60909SourceContributionAnalysis,
)
from power_fault_analyzer.results import (
    EngineeringStudyReportBuilder,
    QuantityAvailability,
    ResultLocationKind,
)
from power_fault_analyzer.standards.iec60909.models import (
    IEC60909CalculationQuantity,
    IEC60909CalculationTrace,
    IEC60909CorrectionFactor,
    IEC60909FactorInput,
    IEC60909QuantityResult,
    IEC60909QuantityStatus,
    IEC60909SourceContribution,
    IEC60909SourceFamily,
    IEC60909SourceMode,
)


def make_short_result(bus_id=None):
    bus_id = bus_id or uuid4()
    return ShortCircuitResult(
        fault_type=FaultType.SINGLE_LINE_TO_GROUND,
        bus_id=bus_id,
        fault_impedance_pu=0.01 + 0.02j,
        base_power_mva=100.0,
        base_voltage_kv=13.8,
        base_current_ka=4.184,
        prefault_sequence_voltages_pu={SequenceType.POSITIVE: 1.0 + 0j},
        driving_point_impedances_pu={
            SequenceType.ZERO: 0.3 + 0.6j,
            SequenceType.POSITIVE: 0.1 + 0.2j,
            SequenceType.NEGATIVE: 0.1 + 0.2j,
        },
        sequence_currents_pu={
            SequenceType.ZERO: 0.7 - 0.2j,
            SequenceType.POSITIVE: 0.7 - 0.2j,
            SequenceType.NEGATIVE: 0.7 - 0.2j,
        },
        sequence_fault_voltages_pu={
            SequenceType.ZERO: 0.01 + 0j,
            SequenceType.POSITIVE: 0.3 + 0.1j,
            SequenceType.NEGATIVE: 0.01 + 0j,
        },
        phase_currents_pu=(2.1 - 0.6j, 0j, 0j),
        phase_voltages_pu=(0.01 + 0j, -0.5 - 0.8j, 0.5 + 0.8j),
        phase_currents_ka=(8.786 - 2.5104j, 0j, 0j),
        phase_voltages_kv=(0.0797 + 0j, -3.9 - 6.2j, 3.9 + 6.2j),
        ground_current_pu=2.1 - 0.6j,
        ground_current_ka=8.786 - 2.5104j,
    )


def make_iec_result(base=None):
    base = base or make_short_result()
    return IEC60909StudyResult(
        standard_edition="IEC 60909-0:2026",
        base_result=base,
        current_case=IEC60909CurrentCase.MAXIMUM,
        voltage_factor=1.1,
        equivalent_voltage_pu=1.1 + 0j,
        initial_symmetrical_current_ka=8.9,
        peak_current_factor=2.4,
        peak_current_ka=21.36,
        breaking_current_ka=8.4,
        steady_state_current_ka=7.8,
        thermal_factor_dc=0.2,
        thermal_factor_ac=1.0,
        thermal_equivalent_current_ka=9.2,
        joule_integral_ka2s=84.64,
        fault_duration_s=1.0,
        frequency_hz=60.0,
        applied_transformer_correction_factors={"KT-T1": 0.98},
        current_method_references={
            "I''k": "IEC60909-0:2026/7.2",
            "ip": "IEC60909-0:2026/8.1",
            "Ib": "IEC60909-0:2026/9.2",
            "Ik": "IEC60909-0:2026/11.2.5",
            "Ith": "IEC60909-0:2026/14/restricted",
            "J": "IEC60909-0:2026/14/restricted",
        },
        unavailable_quantity_reasons={
            "iDC": "Clause 10 normative method unavailable in this supported subset.",
            "Ibasym": "Clause 10 normative method unavailable in this supported subset.",
        },
        first_pole_contact_separation_time_s=0.08,
        dc_component_at_separation_ka=1.2,
        asymmetrical_breaking_current_ka=8.49,
    )


def test_short_circuit_result_is_normalized_with_phase_and_sequence_phasors():
    source = make_short_result()
    report = (
        EngineeringStudyReportBuilder(
            project_name="PFA",
            study_name="Bus fault",
            generated_at=datetime(2026, 1, 1, tzinfo=UTC),
            network=SimpleNamespace(
                name="Test network",
                buses=(SimpleNamespace(id=source.bus_id, name="BUS-13"),),
            ),
        )
        .add_short_circuit_result(source)
        .build()
    )
    fault = report.faults[0]
    assert fault.location_kind is ResultLocationKind.BUS
    assert fault.location_name == "BUS-13"
    assert report.metadata.network_name == "Test network"
    assert [item.phase for item in fault.phase_quantities] == ["A", "B", "C"]
    assert fault.phase_quantities[0].current_ka.magnitude == pytest.approx(abs(8.786 - 2.5104j))
    assert {item.sequence for item in fault.sequence_quantities} == {"zero", "positive", "negative"}
    assert fault.ground_current_ka.magnitude == pytest.approx(abs(8.786 - 2.5104j))


def test_iec_result_preserves_calculated_unavailable_and_supplementary_statuses():
    report = (
        EngineeringStudyReportBuilder(project_name="PFA", study_name="IEC study")
        .add_iec60909_result(make_iec_result(), location_name="BUS-13")
        .build()
    )
    fault = report.faults[0]
    assert report.metadata.standard_edition == "IEC 60909-0:2026"
    quantities = {item.name: item for item in fault.iec_quantities}
    assert quantities["I''k"].status is QuantityAvailability.CALCULATED
    assert quantities["I''k"].value == pytest.approx(8.9)
    assert quantities["iDC"].status is QuantityAvailability.UNAVAILABLE
    assert quantities["iDC"].value is None
    assert quantities["iDC_RL_supplement"].classification == "supplementary"
    assert quantities["iDC_RL_supplement"].value == pytest.approx(1.2)
    assert fault.correction_factors[0].name == "KT-T1"
    assert fault.voltage_factor == pytest.approx(1.1)
    assert fault.frequency_hz == pytest.approx(60.0)
    assert fault.fault_duration_s == pytest.approx(1.0)
    assert fault.first_pole_contact_separation_time_s == pytest.approx(0.08)


def test_line_fault_adds_terminal_branch_currents_without_inventing_transformer_currents():
    base = make_short_result()
    from_bus, to_bus = uuid4(), uuid4()

    def terminal(bus_id, sign):
        return LineTerminalState(
            bus_id=bus_id,
            base_voltage_kv=13.8,
            base_current_ka=4.184,
            sequence_voltages_pu={SequenceType.POSITIVE: 1 + 0j},
            sequence_currents_into_line_pu={SequenceType.POSITIVE: sign * (1 - 0.2j)},
            phase_voltages_pu=(1 + 0j, -0.5 - 0.866j, -0.5 + 0.866j),
            phase_voltages_kv=(7.967 + 0j, -3.983 - 6.9j, -3.983 + 6.9j),
            phase_currents_into_line_pu=(sign * (1 - 0.2j), 0j, 0j),
            phase_currents_into_line_ka=(sign * (4.0 - 0.8j), 0j, 0j),
        )

    line_result = LineFaultStudyResult(
        branch_id=uuid4(),
        line_name="L-01",
        from_bus_id=from_bus,
        to_bus_id=to_bus,
        fault_node_id=base.bus_id,
        fraction_from=0.25,
        line_length_km=12.0,
        distance_from_km=3.0,
        distance_to_km=9.0,
        fault_result=base,
        from_terminal=terminal(from_bus, 1),
        to_terminal=terminal(to_bus, -1),
    )
    report = (
        EngineeringStudyReportBuilder(project_name="PFA", study_name="Line fault")
        .add_line_fault_result(line_result)
        .build()
    )
    assert report.faults[0].location_kind is ResultLocationKind.LINE_INTERIOR
    assert report.faults[0].distance_from_km == pytest.approx(3.0)
    assert len(report.branch_currents) == 6
    assert {item.terminal for item in report.branch_currents} == {"from", "to"}
    assert {item.phase for item in report.branch_currents} == {"A", "B", "C"}


def test_source_contribution_analysis_is_linked_to_fault_and_keeps_phasors():
    base = make_short_result()
    scenario_id, source_id = uuid4(), uuid4()
    contribution = IEC60909SourceContribution(
        source_id=source_id,
        source_name="Grid 1",
        source_family=IEC60909SourceFamily.NETWORK_FEEDER,
        source_mode=IEC60909SourceMode.VOLTAGE_SOURCE,
        sequence_currents_ka={SequenceType.POSITIVE: 4.0 - 0.5j},
        phase_currents_ka={"A": 4.0 - 0.5j},
        model_reference="Utility Thevenin equivalent",
    )
    factor = IEC60909CorrectionFactor(
        name="Source correction",
        value=0.97,
        unit="pu",
        clause_reference="6.3.2",
        inputs=(IEC60909FactorInput(name="rated_voltage", value=13.8, unit="kV"),),
        source_id=source_id,
        scenario_id=scenario_id,
    )
    trace_quantity = IEC60909QuantityResult(
        quantity=IEC60909CalculationQuantity.PEAK_CURRENT,
        status=IEC60909QuantityStatus.CALCULATED,
        value=12.0,
        unit="kA",
        method_id="IEC60909-0:2026/8.1",
    )
    trace = IEC60909CalculationTrace(
        scenario_id=scenario_id,
        source_contributions=(contribution,),
        applied_factors=(factor,),
        quantity_results=(trace_quantity,),
        method_ids={IEC60909CalculationQuantity.PEAK_CURRENT: trace_quantity.method_id},
        assumptions=("Linear superposition over declared source models.",),
        standard_edition="IEC 60909-0:2026",
    )
    analysis = IEC60909SourceContributionAnalysis(
        scenario_id=scenario_id,
        total_result=base,
        source_contributions=(contribution,),
        sequence_balance_residual_ka={SequenceType.POSITIVE: 0.0},
        phase_balance_residual_ka={"A": 0.0},
        trace=trace,
    )
    builder = EngineeringStudyReportBuilder(project_name="PFA", study_name="Sources")
    builder.add_short_circuit_result(base)
    report = builder.add_source_contribution_analysis(analysis).build()
    assert len(report.source_contributions) == 2
    assert {item.domain for item in report.source_contributions} == {"phase", "sequence"}
    assert report.assumptions == ("Linear superposition over declared source models.",)
    assert all(item.fault_id == str(base.bus_id) for item in report.source_contributions)
    assert len(report.source_balance_residuals) == 2
    assert {item.domain for item in report.source_balance_residuals} == {"phase", "sequence"}
    assert all(item.residual_ka == pytest.approx(0.0) for item in report.source_balance_residuals)
    fault = report.faults[0]
    assert any(
        item.name == "Source correction" and "clause 6.3.2" in item.provenance
        for item in fault.correction_factors
    )
    peak = next(item for item in fault.iec_quantities if item.name == "ip")
    assert peak.value == pytest.approx(12.0)
    assert peak.method_reference == "IEC60909-0:2026/8.1"


def test_builder_requires_fault_and_rejects_duplicate_fault_ids():
    builder = EngineeringStudyReportBuilder(project_name="PFA", study_name="Empty")
    with pytest.raises(ValueError, match="At least one fault"):
        builder.build()
    result = make_short_result()
    builder.add_short_circuit_result(result)
    with pytest.raises(ValueError, match="Duplicate fault_id"):
        builder.add_short_circuit_result(result)


def test_builder_rejects_mixed_standard_editions():
    builder = EngineeringStudyReportBuilder(project_name="PFA", study_name="Mixed")
    builder.add_iec60909_result(make_iec_result())
    another = make_iec_result()
    object.__setattr__(another, "standard_edition", "IEC 60909-0:2016")
    with pytest.raises(ValueError, match="mix calculation standard editions"):
        builder.add_iec60909_result(another, fault_id="another")


def test_builder_preserves_absent_sequence_current_as_missing_not_zero():
    original = make_short_result()
    source = replace(
        original,
        sequence_currents_pu={SequenceType.POSITIVE: 0.7 - 0.2j},
        sequence_fault_voltages_pu={
            SequenceType.ZERO: 0j,
            SequenceType.POSITIVE: 0.3 + 0.1j,
        },
        driving_point_impedances_pu={
            SequenceType.ZERO: 0.3 + 0.6j,
            SequenceType.POSITIVE: 0.1 + 0.2j,
        },
    )
    report = (
        EngineeringStudyReportBuilder(project_name="PFA", study_name="Missing sequence data")
        .add_short_circuit_result(source)
        .build()
    )
    sequences = {item.sequence: item for item in report.faults[0].sequence_quantities}
    assert sequences["zero"].current_pu is None
    assert sequences["zero"].voltage_pu is not None
    assert sequences["zero"].voltage_pu.magnitude == pytest.approx(0.0)
