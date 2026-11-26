from __future__ import annotations

from dataclasses import FrozenInstanceError
from uuid import uuid4

import pytest

from power_fault_analyzer.domain.enums.fault_type import FaultType
from power_fault_analyzer.domain.enums.iec60909 import IEC60909CurrentCase
from power_fault_analyzer.domain.enums.sequence_type import SequenceType
from power_fault_analyzer.domain.value_objects.fault_specification import FaultSpecification
from power_fault_analyzer.domain.value_objects.iec60909_study import IEC60909StudySpecification
from power_fault_analyzer.network.sequence_networks.models import SystemBaseSet
from power_fault_analyzer.standards.iec60909 import (
    IEC60909CalculationQuantity,
    IEC60909CalculationTrace,
    IEC60909CorrectionFactor,
    IEC60909CorrectionFactorSet,
    IEC60909CurrentCalculationRequest,
    IEC60909FactorInput,
    IEC60909QuantityResult,
    IEC60909QuantityStatus,
    IEC60909SourceContribution,
    IEC60909SourceDescriptor,
    IEC60909SourceFamily,
    IEC60909SourceMode,
    IEC60909StudyScenario,
    IEC60909TopologyClass,
    validate_factor_references,
    validate_strategy_result,
)


def make_study() -> IEC60909StudySpecification:
    return IEC60909StudySpecification(
        current_case=IEC60909CurrentCase.MAXIMUM,
        fault_duration_s=1.0,
        frequency_hz=50.0,
    )


def make_source_descriptor(
    source_id=None,
    *,
    family=IEC60909SourceFamily.NETWORK_FEEDER,
    mode=IEC60909SourceMode.VOLTAGE_SOURCE,
    active_sequences=frozenset(SequenceType),
):
    return IEC60909SourceDescriptor(
        source_id=source_id or uuid4(),
        name="GRID-1",
        family=family,
        mode=mode,
        active_sequences=active_sequences,
        model_reference="validated-input:GRID-1",
    )


def make_source_contribution(
    source_id,
    *,
    sequence_currents=None,
    phase_currents=None,
    source_name="GRID-1",
    model_reference="validated-input:GRID-1",
):
    return IEC60909SourceContribution(
        source_id=source_id,
        source_name=source_name,
        source_family=IEC60909SourceFamily.NETWORK_FEEDER,
        source_mode=IEC60909SourceMode.VOLTAGE_SOURCE,
        sequence_currents_ka=(
            {SequenceType.POSITIVE: 1.0 + 0.2j} if sequence_currents is None else sequence_currents
        ),
        phase_currents_ka={} if phase_currents is None else phase_currents,
        model_reference=model_reference,
    )


def make_scenario(*, sources=None, equipment_ids=(), fault_type=FaultType.THREE_PHASE):
    bus_id = uuid4()
    return IEC60909StudyScenario(
        network_id=uuid4(),
        fault=FaultSpecification(fault_type, bus_id),
        system_base=SystemBaseSet(100.0, {bus_id: 13.8}),
        study=make_study(),
        topology_class=IEC60909TopologyClass.RADIAL,
        sources=tuple(sources or ()),
        active_equipment_ids=tuple(equipment_ids),
        assumptions=("Bolted bus fault",),
    )


def make_factor(scenario_id, *, source_id=None, equipment_id=None, factor_id=None):
    return IEC60909CorrectionFactor(
        name="test_factor",
        value=1.1,
        unit="dimensionless",
        clause_reference="clause-reference-to-be-confirmed",
        inputs=(IEC60909FactorInput("nominal_voltage", 13.8, "kV"),),
        source_id=source_id,
        equipment_id=equipment_id,
        scenario_id=scenario_id,
        factor_id=factor_id or uuid4(),
    )


def test_source_descriptor_requires_explicit_nonempty_model_and_sequences():
    with pytest.raises(ValueError, match="at least one active sequence"):
        make_source_descriptor(active_sequences=frozenset())

    descriptor = make_source_descriptor(active_sequences=frozenset({SequenceType.POSITIVE}))
    assert descriptor.active_sequences == frozenset({SequenceType.POSITIVE})
    with pytest.raises(FrozenInstanceError):
        descriptor.in_service = False


def test_source_contribution_preserves_complex_phasors_and_is_immutable():
    source_id = uuid4()
    input_currents = {SequenceType.POSITIVE: 1.0 + 0.5j}
    contribution = make_source_contribution(source_id, sequence_currents=input_currents)
    input_currents[SequenceType.POSITIVE] = 99.0 + 0.0j

    assert contribution.sequence_currents_ka[SequenceType.POSITIVE] == 1.0 + 0.5j
    with pytest.raises(TypeError):
        contribution.sequence_currents_ka[SequenceType.POSITIVE] = 2.0 + 0.0j


def test_source_contribution_requires_current_phasors_and_canonical_phase_labels():
    source_id = uuid4()
    with pytest.raises(ValueError, match="must contain"):
        make_source_contribution(source_id, sequence_currents={}, phase_currents={})
    with pytest.raises(ValueError, match="canonical"):
        make_source_contribution(source_id, sequence_currents={}, phase_currents={"L1": 1.0})
    with pytest.raises(ValueError, match="finite"):
        make_source_contribution(
            source_id,
            sequence_currents={SequenceType.ZERO: complex(float("inf"), 0.0)},
        )


def test_factor_requires_positive_value_and_clause_provenance():
    scenario_id = uuid4()
    with pytest.raises(ValueError, match="clause_reference"):
        IEC60909CorrectionFactor(
            name="KT",
            value=1.0,
            unit="dimensionless",
            clause_reference=" ",
            inputs=(),
            scenario_id=scenario_id,
        )
    with pytest.raises(ValueError, match="greater than zero"):
        make_factor(scenario_id, factor_id=uuid4()).__class__(
            name="KT",
            value=0.0,
            unit="dimensionless",
            clause_reference="clause-reference-to-be-confirmed",
            inputs=(),
            scenario_id=scenario_id,
        )


def test_factor_inputs_and_factor_records_are_immutable():
    with pytest.raises(ValueError, match="finite"):
        IEC60909FactorInput("temperature", float("nan"), "degC")
    factor = make_factor(uuid4())
    with pytest.raises(FrozenInstanceError):
        factor.value = 1.2


def test_quantity_result_distinguishes_unavailable_from_zero():
    unavailable = IEC60909QuantityResult(
        quantity=IEC60909CalculationQuantity.PEAK_CURRENT,
        status=IEC60909QuantityStatus.UNAVAILABLE,
        value=None,
        unit="kA",
        reason="No applicable peak-current strategy is implemented for this case.",
    )
    calculated_zero = IEC60909QuantityResult(
        quantity=IEC60909CalculationQuantity.PEAK_CURRENT,
        status=IEC60909QuantityStatus.CALCULATED,
        value=0.0,
        unit="kA",
        method_id="test.peak.v1",
    )
    assert unavailable.value is None
    assert calculated_zero.value == 0.0
    with pytest.raises(ValueError, match="must not carry a value"):
        IEC60909QuantityResult(
            quantity=IEC60909CalculationQuantity.PEAK_CURRENT,
            status=IEC60909QuantityStatus.NOT_APPLICABLE,
            value=0.0,
            unit="kA",
            reason="Not applicable.",
        )


def test_quantity_result_enforces_dimensionally_consistent_units():
    with pytest.raises(ValueError, match=r"kA\^2 s"):
        IEC60909QuantityResult(
            quantity=IEC60909CalculationQuantity.JOULE_INTEGRAL,
            status=IEC60909QuantityStatus.CALCULATED,
            value=10.0,
            unit="kA",
            method_id="test.joule.v1",
        )


def test_study_scenario_requires_fault_bus_base_and_unique_sources():
    descriptor = make_source_descriptor()
    scenario = make_scenario(sources=(descriptor,))
    assert scenario.current_case is IEC60909CurrentCase.MAXIMUM
    with pytest.raises(ValueError, match="repeat a source ID"):
        make_scenario(sources=(descriptor, descriptor))

    wrong_bus = uuid4()
    with pytest.raises(ValueError, match="configured system voltage base"):
        IEC60909StudyScenario(
            network_id=uuid4(),
            fault=FaultSpecification(FaultType.THREE_PHASE, wrong_bus),
            system_base=SystemBaseSet(100.0, {uuid4(): 13.8}),
            study=make_study(),
            topology_class=IEC60909TopologyClass.UNKNOWN,
        )


def test_factor_set_rejects_duplicate_factor_scope_and_wrong_scenario():
    scenario_id = uuid4()
    factor = make_factor(scenario_id)
    with pytest.raises(ValueError, match="repeat the same factor scope"):
        IEC60909CorrectionFactorSet(scenario_id, (factor, make_factor(scenario_id)))
    with pytest.raises(ValueError, match="belong to the factor-set scenario"):
        IEC60909CorrectionFactorSet(uuid4(), (factor,))


def test_factor_reference_validation_rejects_unknown_source_or_equipment():
    descriptor = make_source_descriptor()
    equipment_id = uuid4()
    scenario = make_scenario(sources=(descriptor,), equipment_ids=(equipment_id,))
    valid = make_factor(
        scenario.scenario_id,
        source_id=descriptor.source_id,
        equipment_id=equipment_id,
    )
    validate_factor_references((valid,), scenario=scenario)

    invalid = make_factor(scenario.scenario_id, source_id=uuid4())
    with pytest.raises(ValueError, match="source outside the scenario"):
        validate_factor_references((invalid,), scenario=scenario)


def test_calculation_request_requires_exact_in_service_source_inventory():
    descriptor = make_source_descriptor()
    scenario = make_scenario(sources=(descriptor,))
    contribution = make_source_contribution(descriptor.source_id)
    factors = IEC60909CorrectionFactorSet(scenario.scenario_id)
    request = IEC60909CurrentCalculationRequest(scenario, (contribution,), factors)
    assert request.source_contributions == (contribution,)

    with pytest.raises(ValueError, match="match the scenario source IDs exactly"):
        IEC60909CurrentCalculationRequest(scenario, (), factors)


def test_calculation_request_rejects_source_family_or_mode_mismatch():
    descriptor = make_source_descriptor()
    scenario = make_scenario(sources=(descriptor,))
    contribution = IEC60909SourceContribution(
        source_id=descriptor.source_id,
        source_name="GRID-1",
        source_family=IEC60909SourceFamily.CONVERTER,
        source_mode=IEC60909SourceMode.CURRENT_SOURCE,
        sequence_currents_ka={SequenceType.POSITIVE: 1.0 + 0.0j},
    )
    with pytest.raises(ValueError, match="does not match its scenario descriptor"):
        IEC60909CurrentCalculationRequest(
            scenario,
            (contribution,),
            IEC60909CorrectionFactorSet(scenario.scenario_id),
        )


def test_calculation_trace_requires_methods_for_every_calculated_quantity():
    scenario_id = uuid4()
    quantity_result = IEC60909QuantityResult(
        quantity=IEC60909CalculationQuantity.INITIAL_SYMMETRICAL_CURRENT,
        status=IEC60909QuantityStatus.CALCULATED,
        value=12.5,
        unit="kA",
        method_id="iec.initial.single_feed.v1",
    )
    with pytest.raises(ValueError, match="method_ids must match exactly"):
        IEC60909CalculationTrace(
            scenario_id=scenario_id,
            quantity_results=(quantity_result,),
        )

    trace = IEC60909CalculationTrace(
        scenario_id=scenario_id,
        quantity_results=(quantity_result,),
        method_ids={
            IEC60909CalculationQuantity.INITIAL_SYMMETRICAL_CURRENT: "iec.initial.single_feed.v1"
        },
        assumptions=("Single voltage-source feeder",),
    )
    assert trace.method_ids[IEC60909CalculationQuantity.INITIAL_SYMMETRICAL_CURRENT] == (
        "iec.initial.single_feed.v1"
    )
    with pytest.raises(TypeError):
        trace.method_ids[IEC60909CalculationQuantity.INITIAL_SYMMETRICAL_CURRENT] = "changed"


def test_strategy_result_validator_enforces_quantity_and_method_identity():
    class PeakStrategy:
        quantity = IEC60909CalculationQuantity.PEAK_CURRENT
        method_id = "iec.peak.radial.v1"

    correct = IEC60909QuantityResult(
        quantity=IEC60909CalculationQuantity.PEAK_CURRENT,
        status=IEC60909QuantityStatus.CALCULATED,
        value=20.0,
        unit="kA",
        method_id="iec.peak.radial.v1",
    )
    validate_strategy_result(PeakStrategy(), correct)

    wrong_method = IEC60909QuantityResult(
        quantity=IEC60909CalculationQuantity.PEAK_CURRENT,
        status=IEC60909QuantityStatus.CALCULATED,
        value=20.0,
        unit="kA",
        method_id="another.method",
    )
    with pytest.raises(ValueError, match="strategy identifier"):
        validate_strategy_result(PeakStrategy(), wrong_method)


def test_factor_must_be_scoped_to_scenario_source_or_equipment():
    with pytest.raises(ValueError, match="must be scoped"):
        IEC60909CorrectionFactor(
            name="KT",
            value=1.0,
            unit="dimensionless",
            clause_reference="clause-reference-to-be-confirmed",
            inputs=(),
        )


def test_calculation_trace_rejects_factor_from_different_standard_edition():
    scenario_id = uuid4()
    factor = IEC60909CorrectionFactor(
        name="KT",
        value=1.0,
        unit="dimensionless",
        clause_reference="clause-reference-to-be-confirmed",
        inputs=(),
        scenario_id=scenario_id,
        standard_edition="IEC 60909-0:2016",
    )
    with pytest.raises(ValueError, match="standard edition"):
        IEC60909CalculationTrace(scenario_id=scenario_id, applied_factors=(factor,))


def test_calculation_request_rejects_duplicate_contribution_ids():
    descriptor = make_source_descriptor()
    scenario = make_scenario(sources=(descriptor,))
    contribution = make_source_contribution(descriptor.source_id)
    with pytest.raises(ValueError, match="cannot repeat"):
        IEC60909CurrentCalculationRequest(
            scenario,
            (contribution, contribution),
            IEC60909CorrectionFactorSet(scenario.scenario_id),
        )


def test_calculation_request_rejects_forged_source_metadata():
    descriptor = make_source_descriptor()
    scenario = make_scenario(sources=(descriptor,))
    contribution = make_source_contribution(
        descriptor.source_id,
        source_name="UNRELATED-SOURCE",
    )
    with pytest.raises(ValueError, match="metadata does not match"):
        IEC60909CurrentCalculationRequest(
            scenario,
            (contribution,),
            IEC60909CorrectionFactorSet(scenario.scenario_id),
        )


def test_current_calculation_request_allows_fault_induced_sequence_components():
    descriptor = make_source_descriptor(active_sequences=frozenset({SequenceType.POSITIVE}))
    scenario = make_scenario(
        sources=(descriptor,),
        fault_type=FaultType.SINGLE_LINE_TO_GROUND,
    )
    contribution = make_source_contribution(
        descriptor.source_id,
        sequence_currents={
            SequenceType.POSITIVE: 1.0 + 0.0j,
            SequenceType.NEGATIVE: -0.4 + 0.0j,
            SequenceType.ZERO: -0.6 + 0.0j,
        },
    )
    request = IEC60909CurrentCalculationRequest(
        scenario,
        (contribution,),
        IEC60909CorrectionFactorSet(scenario.scenario_id),
    )
    assert request.source_contributions == (contribution,)
