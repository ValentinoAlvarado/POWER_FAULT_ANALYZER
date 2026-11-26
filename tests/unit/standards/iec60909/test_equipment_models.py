from __future__ import annotations

from uuid import uuid4

import pytest

from power_fault_analyzer.domain.aggregates.network import Network
from power_fault_analyzer.domain.entities.bus import Bus
from power_fault_analyzer.domain.entities.terminal import Terminal
from power_fault_analyzer.domain.enums.fault_type import FaultType
from power_fault_analyzer.domain.enums.iec60909 import IEC60909CurrentCase
from power_fault_analyzer.domain.enums.sequence_source_kind import SequenceSourceKind
from power_fault_analyzer.domain.enums.sequence_type import SequenceType
from power_fault_analyzer.domain.enums.source_operating_regime import SourceOperatingRegime
from power_fault_analyzer.domain.enums.winding_connection import WindingConnection
from power_fault_analyzer.domain.enums.winding_designation import WindingDesignation
from power_fault_analyzer.domain.value_objects.electrical_impedance_base import (
    ElectricalImpedanceBase,
)
from power_fault_analyzer.domain.value_objects.fault_specification import FaultSpecification
from power_fault_analyzer.domain.value_objects.frequency import Frequency
from power_fault_analyzer.domain.value_objects.iec60909_study import IEC60909StudySpecification
from power_fault_analyzer.domain.value_objects.neutral_grounding import NeutralGrounding
from power_fault_analyzer.domain.value_objects.per_unit_impedance import PerUnitImpedance
from power_fault_analyzer.domain.value_objects.source_models import InductionMotorParameters
from power_fault_analyzer.domain.value_objects.three_winding_zero_sequence import (
    ThreeWindingZeroSequencePortModel,
)
from power_fault_analyzer.domain.value_objects.transformer_impedance import (
    PairwiseTransformerImpedances,
    SequencePerUnitImpedance,
)
from power_fault_analyzer.domain.value_objects.transformer_winding import TransformerWinding
from power_fault_analyzer.domain.value_objects.vector_group import VectorGroup
from power_fault_analyzer.domain.value_objects.voltage import Voltage
from power_fault_analyzer.equipment.motors import InductionMotor
from power_fault_analyzer.equipment.transformers import ThreeWindingTransformer
from power_fault_analyzer.network.sequence_networks.builder import SequenceNetworkBuilder
from power_fault_analyzer.network.sequence_networks.models import SystemBaseSet
from power_fault_analyzer.standards.iec60909 import (
    IEC60909CurrentSourceInput,
    IEC60909InductionMotorInput,
    IEC60909SourceDescriptor,
    IEC60909SourceFamily,
    IEC60909SourceMode,
    IEC60909StudyScenario,
    IEC60909TopologyClass,
    IEC60909TransformerReadinessStatus,
    validate_iec60909_current_source_input,
)
from power_fault_analyzer.standards.iec60909.equipment_models import (
    IEC60909ThreeWindingTransformerCorrectionInput,
)
from power_fault_analyzer.standards.iec60909.source_inventory import (
    IEC60909SourceInventoryBuilder,
)


def make_motor(*, grounded: bool = True) -> InductionMotor:
    equipment_id = uuid4()
    base = ElectricalImpedanceBase(20.0, 13.8)
    parameters = InductionMotorParameters(
        rated_power_mva=20.0,
        sequence_impedances=SequencePerUnitImpedance(
            base=base,
            positive=PerUnitImpedance(0.02, 0.22),
            negative=PerUnitImpedance(0.03, 0.25),
            zero=PerUnitImpedance(0.04, 0.12),
        ),
        decay_time_constant_s=0.08,
        data_reference="vendor-test-report:IM-20MVA-01",
        prefault_voltage_pu=0.97 - 0.02j,
    )
    return InductionMotor(
        id=equipment_id,
        name="IM-20MVA-01",
        terminal=Terminal(equipment_id, "P", Voltage.from_kv(13.8)),
        frequency=Frequency(60.0),
        parameters=parameters,
        neutral_grounding=NeutralGrounding.solid() if grounded else NeutralGrounding.ungrounded(),
    )


def make_scenario(
    descriptor: IEC60909SourceDescriptor,
    *,
    fault_type: FaultType = FaultType.THREE_PHASE,
) -> IEC60909StudyScenario:
    bus_id = uuid4()
    return IEC60909StudyScenario(
        network_id=uuid4(),
        fault=FaultSpecification(fault_type, bus_id),
        system_base=SystemBaseSet(100.0, {bus_id: 13.8}),
        study=IEC60909StudySpecification(
            current_case=IEC60909CurrentCase.MAXIMUM,
            fault_duration_s=1.0,
            frequency_hz=50.0,
        ),
        topology_class=IEC60909TopologyClass.RADIAL,
        sources=(descriptor,),
    )


def make_three_winding_transformer(*, with_zero_sequence: bool) -> ThreeWindingTransformer:
    equipment_id = uuid4()
    windings = (
        TransformerWinding(
            WindingDesignation.HIGH_VOLTAGE,
            220.0,
            100.0,
            WindingConnection.STAR,
            NeutralGrounding.solid(),
            neutral_terminal_available=True,
        ),
        TransformerWinding(
            WindingDesignation.MEDIUM_VOLTAGE,
            66.0,
            60.0,
            WindingConnection.DELTA,
            None,
        ),
        TransformerWinding(
            WindingDesignation.LOW_VOLTAGE,
            13.8,
            40.0,
            WindingConnection.STAR,
            NeutralGrounding.ungrounded(),
        ),
    )
    terminals = (
        Terminal(equipment_id, "HV", Voltage.from_kv(220.0)),
        Terminal(equipment_id, "MV", Voltage.from_kv(66.0)),
        Terminal(equipment_id, "LV", Voltage.from_kv(13.8)),
    )
    base = ElectricalImpedanceBase(100.0, 220.0)

    def sequence_impedance(value: complex, zero_multiplier: float) -> SequencePerUnitImpedance:
        return SequencePerUnitImpedance(
            base,
            PerUnitImpedance(value.real, value.imag),
            PerUnitImpedance(value.real * 1.05, value.imag * 1.02),
            PerUnitImpedance(value.real * zero_multiplier, value.imag * zero_multiplier),
        )

    zero_model = None
    if with_zero_sequence:
        zero_model = ThreeWindingZeroSequencePortModel(
            base=base,
            impedance_matrix_pu=(
                (0.30 + 0.10j, 0.0 + 0.0j, 0.0 + 0.0j),
                (0.0 + 0.0j, 0.40 + 0.10j, 0.0 + 0.0j),
                (0.0 + 0.0j, 0.0 + 0.0j, 0.50 + 0.10j),
            ),
            reference="vendor-zero-sequence-test:TR-3W-01",
        )
    return ThreeWindingTransformer(
        id=equipment_id,
        name="TR-3W-01",
        terminals=terminals,
        windings=windings,
        frequency=Frequency(50.0),
        hv_mv_vector_group=VectorGroup(WindingConnection.STAR, WindingConnection.DELTA, 11),
        hv_lv_vector_group=VectorGroup(WindingConnection.STAR, WindingConnection.STAR, 0),
        pairwise_impedances=PairwiseTransformerImpedances(
            sequence_impedance(0.12 + 0.36j, 1.7),
            sequence_impedance(0.16 + 0.48j, 1.5),
            sequence_impedance(0.10 + 0.30j, 1.9),
        ),
        zero_sequence_port_model=zero_model,
    )


def test_iec_current_source_requires_sequence_keys_and_preserves_provenance():
    descriptor = IEC60909SourceDescriptor(
        source_id=uuid4(),
        name="BESS-PCS-1",
        family=IEC60909SourceFamily.CONVERTER,
        mode=IEC60909SourceMode.CURRENT_SOURCE,
        active_sequences=frozenset(SequenceType),
        model_reference="iec-current-source:vendor-model-42",
    )
    data = IEC60909CurrentSourceInput(
        source_id=descriptor.source_id,
        source_family=IEC60909SourceFamily.CONVERTER,
        rated_voltage_kv=13.8,
        sequence_currents_ka={
            SequenceType.POSITIVE: 2.0 - 0.1j,
            SequenceType.NEGATIVE: None,
            SequenceType.ZERO: None,
        },
        data_reference="vendor-report:PCS-42",
        method_reference="IEC 60909-0:2026, 5.2.3 / reviewed calculation record",
    )
    validate_iec60909_current_source_input(data, make_scenario(descriptor))
    per_unit = data.to_per_unit(ElectricalImpedanceBase(2.0 * 3.0**0.5 * 13.8, 13.8))
    assert per_unit[SequenceType.POSITIVE] == pytest.approx(1.0 - 0.05j)
    assert SequenceType.NEGATIVE not in per_unit
    with pytest.raises(ValueError, match="voltage must match"):
        data.to_per_unit(ElectricalImpedanceBase(100.0, 11.0))
    with pytest.raises(TypeError):
        data.sequence_currents_ka[SequenceType.POSITIVE] = 0j


def test_iec_current_source_preserves_explicit_zero_sequence_phasors():
    data = IEC60909CurrentSourceInput(
        source_id=uuid4(),
        source_family=IEC60909SourceFamily.CONVERTER,
        rated_voltage_kv=13.8,
        sequence_currents_ka={
            SequenceType.POSITIVE: 1.5 + 0.0j,
            SequenceType.NEGATIVE: 0.0j,
            SequenceType.ZERO: 0.0j,
        },
        data_reference="vendor-report:PCS-EXPLICIT-ZERO",
        method_reference="reviewed IEC current-source calculation",
    )
    per_unit = data.to_per_unit(ElectricalImpedanceBase(100.0, 13.8))
    assert SequenceType.NEGATIVE in per_unit
    assert per_unit[SequenceType.NEGATIVE] == 0j
    assert SequenceType.ZERO in per_unit
    assert per_unit[SequenceType.ZERO] == 0j


def test_iec_current_source_rejects_implicit_missing_sequence():
    with pytest.raises(ValueError, match="explicitly declare"):
        IEC60909CurrentSourceInput(
            source_id=uuid4(),
            source_family=IEC60909SourceFamily.CONVERTER,
            rated_voltage_kv=13.8,
            sequence_currents_ka={SequenceType.POSITIVE: 1.0 + 0.0j},
            data_reference="vendor-report:PCS-42",
            method_reference="reviewed IEC procedure",
        )


def test_iec_current_source_rejects_unspecified_required_sequence_for_ground_fault():
    descriptor = IEC60909SourceDescriptor(
        source_id=uuid4(),
        name="PCS-1",
        family=IEC60909SourceFamily.CONVERTER,
        mode=IEC60909SourceMode.CURRENT_SOURCE,
        active_sequences=frozenset(SequenceType),
        model_reference="iec-current-source:PCS-1",
    )
    data = IEC60909CurrentSourceInput(
        source_id=descriptor.source_id,
        source_family=IEC60909SourceFamily.CONVERTER,
        rated_voltage_kv=13.8,
        sequence_currents_ka={
            SequenceType.POSITIVE: 1.0 + 0.0j,
            SequenceType.NEGATIVE: 0.0j,
            SequenceType.ZERO: None,
        },
        data_reference="vendor-report:PCS-1",
        method_reference="reviewed IEC procedure",
    )
    scenario = make_scenario(descriptor, fault_type=FaultType.SINGLE_LINE_TO_GROUND)
    with pytest.raises(ValueError, match="zero.*explicitly established"):
        validate_iec60909_current_source_input(data, scenario)


def test_iec_current_source_rejects_voltage_source_descriptor():
    descriptor = IEC60909SourceDescriptor(
        source_id=uuid4(),
        name="PCS-1",
        family=IEC60909SourceFamily.CONVERTER,
        mode=IEC60909SourceMode.VOLTAGE_SOURCE,
        active_sequences=frozenset({SequenceType.POSITIVE}),
        model_reference="explicit-sequence-current-command",
    )
    data = IEC60909CurrentSourceInput(
        source_id=descriptor.source_id,
        source_family=IEC60909SourceFamily.CONVERTER,
        rated_voltage_kv=13.8,
        sequence_currents_ka={
            SequenceType.POSITIVE: 1.0 + 0.0j,
            SequenceType.NEGATIVE: 0.0j,
            SequenceType.ZERO: 0.0j,
        },
        data_reference="vendor-report:PCS-1",
        method_reference="reviewed IEC procedure",
    )
    with pytest.raises(ValueError, match="voltage-source descriptor"):
        validate_iec60909_current_source_input(data, make_scenario(descriptor))


def test_iec_current_source_rejects_family_or_source_identity_mismatch():
    descriptor = IEC60909SourceDescriptor(
        source_id=uuid4(),
        name="PSU-1",
        family=IEC60909SourceFamily.POWER_STATION_UNIT,
        mode=IEC60909SourceMode.CURRENT_SOURCE,
        active_sequences=frozenset(SequenceType),
        model_reference="iec-current-source:PSU-1",
    )
    wrong_family = IEC60909CurrentSourceInput(
        source_id=descriptor.source_id,
        source_family=IEC60909SourceFamily.CONVERTER,
        rated_voltage_kv=13.8,
        sequence_currents_ka={sequence: 0.0j for sequence in SequenceType},
        data_reference="psu-data-sheet:PSU-1",
        method_reference="reviewed IEC procedure",
    )
    with pytest.raises(ValueError, match="family does not match"):
        validate_iec60909_current_source_input(wrong_family, make_scenario(descriptor))

    unknown_source = IEC60909CurrentSourceInput(
        source_id=uuid4(),
        source_family=IEC60909SourceFamily.POWER_STATION_UNIT,
        rated_voltage_kv=13.8,
        sequence_currents_ka={sequence: 0.0j for sequence in SequenceType},
        data_reference="psu-data-sheet:PSU-1",
        method_reference="reviewed IEC procedure",
    )
    with pytest.raises(ValueError, match="exactly one scenario source"):
        validate_iec60909_current_source_input(unknown_source, make_scenario(descriptor))


def test_induction_motor_parameter_base_power_must_match_machine_rating():
    with pytest.raises(ValueError, match="base power must match"):
        InductionMotorParameters(
            rated_power_mva=20.0,
            sequence_impedances=SequencePerUnitImpedance(
                base=ElectricalImpedanceBase(25.0, 13.8),
                positive=PerUnitImpedance(0.02, 0.22),
                negative=PerUnitImpedance(0.03, 0.25),
                zero=PerUnitImpedance(0.04, 0.12),
            ),
            decay_time_constant_s=0.08,
            data_reference="vendor-test-report:IM-20MVA-01",
        )


def test_induction_motor_builds_only_its_explicit_initial_equivalent():
    motor = make_motor(grounded=True)
    equivalent = motor.build_source_equivalent(
        ElectricalImpedanceBase(100.0, 13.8),
        regime=SourceOperatingRegime.SUBTRANSIENT,
    )
    assert motor.family.value == "motor"
    assert equivalent.positive.status.value == "available"
    assert equivalent.negative.status.value == "available"
    assert equivalent.zero.status.value == "available"
    assert equivalent.positive.internal_voltage_pu == pytest.approx(0.97 - 0.02j)


def test_induction_motor_does_not_infer_zero_sequence_return_path():
    motor = make_motor(grounded=False)
    equivalent = motor.build_source_equivalent(
        ElectricalImpedanceBase(100.0, 13.8),
        regime=SourceOperatingRegime.SUBTRANSIENT,
    )
    assert equivalent.zero.status.value == "blocked"


def test_induction_motor_integrates_into_sequence_network_and_inventory():
    motor = make_motor(grounded=True)
    network = Network("Motor source network")
    bus = Bus("BUS-MOTOR", Voltage.from_kv(13.8))
    network.add_bus(bus)
    network.add_equipment(motor)
    network.connect(motor.terminals[0].id, bus.id)
    system_base = SystemBaseSet(100.0, {bus.id: 13.8})
    networks = SequenceNetworkBuilder(system_base).build_all(network)

    for sequence in (SequenceType.POSITIVE, SequenceType.NEGATIVE, SequenceType.ZERO):
        source_shunt = next(
            item for item in networks.for_sequence(sequence).shunts if item.id == motor.id
        )
        assert source_shunt.source_kind is SequenceSourceKind.ASYNCHRONOUS_MACHINE

    inventory = IEC60909SourceInventoryBuilder().build(network, networks)
    descriptor = next(item for item in inventory if item.source_id == motor.id)
    assert descriptor.family is IEC60909SourceFamily.ASYNCHRONOUS_MACHINE
    assert descriptor.mode is IEC60909SourceMode.VOLTAGE_SOURCE


def test_iec_induction_motor_input_is_traceable_and_matches_equipment():
    motor = make_motor()
    data = IEC60909InductionMotorInput.from_equipment(motor)
    assert data.equipment_id == motor.id
    assert data.rated_power_mva == pytest.approx(20.0)
    assert data.rated_voltage_kv == pytest.approx(13.8)
    assert data.data_reference == "vendor-test-report:IM-20MVA-01"
    assert data.frequency_hz == pytest.approx(60.0)


def test_three_winding_transformer_requires_explicit_zero_sequence_and_test_references():
    transformer = make_three_winding_transformer(with_zero_sequence=False)
    readiness = IEC60909ThreeWindingTransformerCorrectionInput.from_equipment(
        transformer,
        test_data_reference="manufacturer-test-report:TR-3W-01",
    )
    assert readiness.status is IEC60909TransformerReadinessStatus.UNAVAILABLE_MISSING_DATA
    assert any("zero-sequence three-port model" in item for item in readiness.missing_requirements)

    transformer_with_z0 = make_three_winding_transformer(with_zero_sequence=True)
    missing_test_reference = IEC60909ThreeWindingTransformerCorrectionInput.from_equipment(
        transformer_with_z0,
        test_data_reference=None,
    )
    assert (
        missing_test_reference.status is IEC60909TransformerReadinessStatus.UNAVAILABLE_MISSING_DATA
    )
    assert any(
        "pairwise short-circuit impedances" in item
        for item in missing_test_reference.missing_requirements
    )


def test_three_winding_transformer_ready_snapshot_preserves_all_ratings_and_references():
    transformer = make_three_winding_transformer(with_zero_sequence=True)
    readiness = IEC60909ThreeWindingTransformerCorrectionInput.from_equipment(
        transformer,
        test_data_reference="manufacturer-test-report:TR-3W-01",
    )
    assert readiness.status is IEC60909TransformerReadinessStatus.READY_FOR_NORMATIVE_POLICY
    assert readiness.missing_requirements == ()
    assert readiness.correction_input is not None
    correction_input = readiness.correction_input
    assert correction_input.rated_power_mva_by_winding == (100.0, 60.0, 40.0)
    assert correction_input.rated_voltage_kv_by_winding == (220.0, 66.0, 13.8)
    assert correction_input.zero_sequence_reference == "vendor-zero-sequence-test:TR-3W-01"
    assert correction_input.test_data_reference == "manufacturer-test-report:TR-3W-01"


def test_three_winding_transformer_readiness_does_not_claim_a_factor_was_calculated():
    transformer = make_three_winding_transformer(with_zero_sequence=True)
    readiness = IEC60909ThreeWindingTransformerCorrectionInput.from_equipment(
        transformer,
        test_data_reference="manufacturer-test-report:TR-3W-01",
    )
    assert readiness.status is IEC60909TransformerReadinessStatus.READY_FOR_NORMATIVE_POLICY
    assert not hasattr(readiness, "factor_value")
