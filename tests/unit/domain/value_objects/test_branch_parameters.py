import pytest

from power_fault_analyzer.domain.enums.sequence_type import SequenceType
from power_fault_analyzer.domain.value_objects.impedance import Admittance, Impedance
from power_fault_analyzer.domain.value_objects.sequence_parameters import (
    AdmittancePerLength,
    ImpedancePerLength,
    SequenceAdmittancePerLengthSet,
    SequenceImpedancePerLengthSet,
)


def test_impedance_keeps_resistance_and_reactance_as_complex_components() -> None:
    value = Impedance(0.12, -0.45)
    assert value.value_ohm == pytest.approx(0.12 - 0.45j)


def test_impedance_rejects_negative_resistance_but_allows_negative_reactance() -> None:
    assert Impedance(0.0, -2.0).reactance_ohm == -2.0
    with pytest.raises(ValueError, match="resistance"):
        Impedance(-0.1, 0.2)


def test_admittance_exposes_complex_siemens() -> None:
    value = Admittance(1e-6, 4e-6)
    assert value.value_siemens == pytest.approx(1e-6 + 4e-6j)


def test_per_length_impedance_scales_with_line_length() -> None:
    value = ImpedancePerLength(0.1, 0.4).for_length(10.0)
    assert value == Impedance(1.0, 4.0)


def test_per_length_admittance_scales_with_line_length() -> None:
    value = AdmittancePerLength(1e-6, 4e-6).for_length(10.0)
    assert value.conductance_siemens == pytest.approx(10e-6)
    assert value.susceptance_siemens == pytest.approx(40e-6)


def test_sequence_impedance_set_does_not_assume_positive_equals_negative() -> None:
    values = SequenceImpedancePerLengthSet(
        positive=ImpedancePerLength(0.1, 0.4),
        negative=ImpedancePerLength(0.12, 0.42),
        zero=ImpedancePerLength(0.3, 1.2),
    )
    assert values.for_sequence(SequenceType.POSITIVE).reactance_ohm_per_km == 0.4
    assert values.for_sequence(SequenceType.NEGATIVE).reactance_ohm_per_km == 0.42
    assert values.for_sequence(SequenceType.ZERO).reactance_ohm_per_km == 1.2


def test_sequence_parameter_set_rejects_non_sequence_impedance() -> None:
    with pytest.raises(TypeError):
        SequenceImpedancePerLengthSet(
            positive=ImpedancePerLength(0.1, 0.4),
            negative=object(),  # type: ignore[arg-type]
            zero=ImpedancePerLength(0.3, 1.2),
        )


def test_sequence_admittance_zero_factory_is_immutable_and_valid() -> None:
    values = SequenceAdmittancePerLengthSet.all_zero()
    assert values.for_sequence(SequenceType.ZERO) == AdmittancePerLength()
