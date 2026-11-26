from dataclasses import FrozenInstanceError

import pytest

from power_fault_analyzer.domain.enums.sequence_type import SequenceType
from power_fault_analyzer.domain.enums.source_sequence_status import SourceSequenceStatus
from power_fault_analyzer.domain.value_objects.electrical_impedance_base import (
    ElectricalImpedanceBase,
)
from power_fault_analyzer.domain.value_objects.source_models import (
    ConverterFaultCurrentCapability,
    ExternalGridShortCircuitData,
    InductionGeneratorParameters,
    SourceEquivalentSet,
    SourceSequenceEquivalent,
    SynchronousMachineSequenceImpedances,
)
from power_fault_analyzer.domain.value_objects.transformer_impedance import (
    PerUnitImpedance,
    SequencePerUnitImpedance,
)


def _sequence_impedances(base: ElectricalImpedanceBase) -> SequencePerUnitImpedance:
    return SequencePerUnitImpedance(
        base=base,
        positive=PerUnitImpedance(0.01, 0.20),
        negative=PerUnitImpedance(0.01, 0.18),
        zero=PerUnitImpedance(0.02, 0.10),
    )


def test_electrical_impedance_base_uses_three_phase_ll_base() -> None:
    base = ElectricalImpedanceBase(100.0, 13.8)
    assert base.base_impedance_ohm == pytest.approx(1.9044)
    assert base.base_current_ka == pytest.approx(4.183697)


@pytest.mark.parametrize(
    ("power", "voltage"),
    [(0.0, 13.8), (100.0, 0.0), (-1.0, 13.8), (100.0, float("inf"))],
)
def test_electrical_impedance_base_rejects_invalid_values(power, voltage) -> None:
    with pytest.raises((TypeError, ValueError)):
        ElectricalImpedanceBase(power, voltage)


def test_source_sequence_equivalent_requires_impedance_when_available() -> None:
    with pytest.raises(ValueError, match="requires an impedance"):
        SourceSequenceEquivalent(
            sequence=SequenceType.NEGATIVE,
            status=SourceSequenceStatus.AVAILABLE,
        )


def test_source_sequence_equivalent_requires_positive_internal_voltage() -> None:
    with pytest.raises(ValueError, match="requires internal voltage"):
        SourceSequenceEquivalent(
            sequence=SequenceType.POSITIVE,
            status=SourceSequenceStatus.AVAILABLE,
            impedance=PerUnitImpedance(0.0, 0.2),
        )


def test_blocked_and_unspecified_are_distinct_states() -> None:
    blocked = SourceSequenceEquivalent.blocked(SequenceType.ZERO)
    unspecified = SourceSequenceEquivalent.unspecified(SequenceType.ZERO)
    assert blocked.status is SourceSequenceStatus.BLOCKED
    assert unspecified.status is SourceSequenceStatus.UNSPECIFIED
    assert blocked != unspecified


def test_source_sequence_equivalent_rejects_emf_on_negative_sequence() -> None:
    with pytest.raises(ValueError, match="only defined for positive sequence"):
        SourceSequenceEquivalent(
            sequence=SequenceType.NEGATIVE,
            status=SourceSequenceStatus.AVAILABLE,
            impedance=PerUnitImpedance(0.0, 0.2),
            internal_voltage_pu=1 + 0j,
        )


def test_source_equivalent_set_requires_correct_sequence_order() -> None:
    positive = SourceSequenceEquivalent(
        SequenceType.POSITIVE,
        SourceSequenceStatus.AVAILABLE,
        PerUnitImpedance(0.0, 0.2),
        1 + 0j,
    )
    with pytest.raises(ValueError, match="negative sequence"):
        SourceEquivalentSet(
            ElectricalImpedanceBase(100, 13.8),
            positive,
            SourceSequenceEquivalent.blocked(SequenceType.ZERO),
            SourceSequenceEquivalent.blocked(SequenceType.ZERO),
        )


def test_source_equivalent_set_positive_sequence_must_be_available() -> None:
    with pytest.raises(ValueError, match="positive-sequence"):
        SourceEquivalentSet(
            ElectricalImpedanceBase(100, 13.8),
            SourceSequenceEquivalent.blocked(SequenceType.POSITIVE),
            SourceSequenceEquivalent.blocked(SequenceType.NEGATIVE),
            SourceSequenceEquivalent.blocked(SequenceType.ZERO),
        )


def test_source_equivalent_set_converts_all_available_sequences_and_preserves_emf() -> None:
    original_base = ElectricalImpedanceBase(100, 13.8)
    target_base = ElectricalImpedanceBase(50, 13.8)
    source = SourceEquivalentSet(
        base=original_base,
        positive=SourceSequenceEquivalent(
            SequenceType.POSITIVE,
            SourceSequenceStatus.AVAILABLE,
            PerUnitImpedance(0.01, 0.2),
            0.98 - 0.03j,
        ),
        negative=SourceSequenceEquivalent(
            SequenceType.NEGATIVE,
            SourceSequenceStatus.AVAILABLE,
            PerUnitImpedance(0.02, 0.18),
        ),
        zero=SourceSequenceEquivalent.blocked(SequenceType.ZERO),
    )
    converted = source.convert_base(target_base)
    assert converted.positive.impedance.value_pu == pytest.approx(0.005 + 0.1j)
    assert converted.negative.impedance.value_pu == pytest.approx(0.01 + 0.09j)
    assert converted.positive.internal_voltage_pu == pytest.approx(0.98 - 0.03j)
    assert converted.zero.status is SourceSequenceStatus.BLOCKED


def test_synchronous_machine_sequence_impedances_select_regimes_and_convert_base() -> None:
    from power_fault_analyzer.domain.enums.source_operating_regime import SourceOperatingRegime

    machine_base = ElectricalImpedanceBase(100, 13.8)
    system_base = ElectricalImpedanceBase(50, 13.8)
    values = SynchronousMachineSequenceImpedances(
        base=machine_base,
        positive_subtransient=PerUnitImpedance(0.01, 0.20),
        positive_transient=PerUnitImpedance(0.02, 0.30),
        positive_synchronous=PerUnitImpedance(0.03, 1.50),
        negative=PerUnitImpedance(0.01, 0.18),
        zero=PerUnitImpedance(0.02, 0.10),
    )
    converted = values.convert_base(system_base)
    assert values.positive_for_regime(SourceOperatingRegime.SUBTRANSIENT).value_pu == 0.01 + 0.2j
    assert values.positive_for_regime(SourceOperatingRegime.TRANSIENT).value_pu == 0.02 + 0.3j
    assert values.positive_for_regime(SourceOperatingRegime.SYNCHRONOUS).value_pu == 0.03 + 1.5j
    assert converted.positive_subtransient.value_pu == pytest.approx(0.005 + 0.1j)


def test_synchronous_machine_impedances_reject_negative_physical_reactance() -> None:
    base = ElectricalImpedanceBase(100, 13.8)
    with pytest.raises(ValueError, match="non-negative"):
        SynchronousMachineSequenceImpedances(
            base,
            PerUnitImpedance(0.01, 0.2),
            PerUnitImpedance(0.02, 0.3),
            PerUnitImpedance(0.03, 1.5),
            PerUnitImpedance(0.01, -0.1),
            PerUnitImpedance(0.02, 0.1),
        )


def test_external_grid_positive_impedance_uses_scc_and_rx_ratio() -> None:
    data = ExternalGridShortCircuitData(short_circuit_power_mva=100.0, rx_ratio=0.1)
    impedance = data.positive_sequence_impedance(13.8)
    assert abs(impedance.value_ohm) == pytest.approx(13.8**2 / 100.0)
    assert impedance.resistance_ohm / impedance.reactance_ohm == pytest.approx(0.1)


@pytest.mark.parametrize(
    ("power", "ratio"),
    [(0, 0.1), (100, -0.1), (float("inf"), 0.1), (100, float("nan"))],
)
def test_external_grid_data_rejects_invalid_scc_or_rx(power, ratio) -> None:
    with pytest.raises((TypeError, ValueError)):
        ExternalGridShortCircuitData(power, ratio)


def test_external_grid_optional_sequences_are_explicit_inputs() -> None:
    data = ExternalGridShortCircuitData(100, 0.1)
    assert data.negative_sequence_impedance_ohm is None
    assert data.zero_sequence_impedance_ohm is None


def test_induction_generator_parameters_are_immutable() -> None:
    params = InductionGeneratorParameters(
        rated_power_mva=20,
        sequence_impedances=_sequence_impedances(ElectricalImpedanceBase(20, 13.8)),
        decay_time_constant_s=0.08,
    )
    with pytest.raises(FrozenInstanceError):
        params.rated_power_mva = 21  # type: ignore[misc]


def test_induction_generator_parameters_reject_non_positive_decay_time() -> None:
    with pytest.raises(ValueError):
        InductionGeneratorParameters(
            rated_power_mva=20,
            sequence_impedances=_sequence_impedances(ElectricalImpedanceBase(20, 13.8)),
            decay_time_constant_s=0,
        )


def test_converter_capability_validates_limits() -> None:
    value = ConverterFaultCurrentCapability(
        base=ElectricalImpedanceBase(10.0, 0.4),
        overall_current_limit_pu=1.2,
        positive_sequence_limit_pu=1.1,
        negative_sequence_limit_pu=0.3,
        zero_sequence_limit_pu=0.0,
    )
    assert value.overall_current_limit_pu == pytest.approx(1.2)
    assert value.zero_sequence_limit_pu == 0.0


def test_converter_capability_rejects_sequence_limit_above_overall() -> None:
    with pytest.raises(ValueError, match="overall"):
        ConverterFaultCurrentCapability(ElectricalImpedanceBase(10.0, 0.4), 1.0, 1.1)


def test_converter_capability_none_means_unspecified_not_zero() -> None:
    value = ConverterFaultCurrentCapability(ElectricalImpedanceBase(10.0, 0.4), 1.2, 1.1)
    assert value.negative_sequence_limit_pu is None
    assert value.zero_sequence_limit_pu is None


def test_source_equivalent_set_rescales_per_unit_voltage_when_voltage_base_changes() -> None:
    source = SourceEquivalentSet(
        base=ElectricalImpedanceBase(100, 13.8),
        positive=SourceSequenceEquivalent(
            SequenceType.POSITIVE,
            SourceSequenceStatus.AVAILABLE,
            PerUnitImpedance(0.01, 0.2),
            1.0 + 0.0j,
        ),
        negative=SourceSequenceEquivalent.blocked(SequenceType.NEGATIVE),
        zero=SourceSequenceEquivalent.blocked(SequenceType.ZERO),
    )
    converted = source.convert_base(ElectricalImpedanceBase(100, 6.9))
    assert converted.positive.internal_voltage_pu == pytest.approx(2.0 + 0.0j)


def test_converter_capability_current_limits_convert_using_current_bases() -> None:
    old_base = ElectricalImpedanceBase(10.0, 13.8)
    new_base = ElectricalImpedanceBase(100.0, 13.8)
    value = ConverterFaultCurrentCapability(
        base=old_base,
        overall_current_limit_pu=1.2,
        positive_sequence_limit_pu=1.1,
        negative_sequence_limit_pu=0.3,
        zero_sequence_limit_pu=0.0,
    )
    converted = value.convert_base(new_base)
    assert converted.overall_current_limit_pu == pytest.approx(0.12)
    assert converted.positive_sequence_limit_pu == pytest.approx(0.11)
    assert converted.negative_sequence_limit_pu == pytest.approx(0.03)
    assert converted.zero_sequence_limit_pu == 0.0
