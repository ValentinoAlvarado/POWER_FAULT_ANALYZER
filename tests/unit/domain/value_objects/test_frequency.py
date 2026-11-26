import pytest

from power_fault_analyzer.domain.value_objects.frequency import Frequency


def test_frequency_accepts_50_and_60_hz() -> None:
    assert Frequency(50.0).value_hz == 50.0
    assert Frequency(60.0).value_hz == 60.0


@pytest.mark.parametrize("value", [0.0, -1.0, float("inf"), float("nan")])
def test_frequency_rejects_non_positive_or_non_finite_values(value: float) -> None:
    with pytest.raises(ValueError):
        Frequency(value)


def test_frequency_rejects_boolean() -> None:
    with pytest.raises(TypeError):
        Frequency(True)  # type: ignore[arg-type]
