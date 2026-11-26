import pytest

from power_fault_analyzer.electrical.per_unit import (
    BaseQuantities,
    convert_pu_base,
    ohm_to_pu,
    pu_to_ohm,
)


def test_base_quantities_for_100_mva_13_8_kv() -> None:
    base = BaseQuantities(s_base_mva=100.0, v_base_kv=13.8)
    assert base.i_base_ka == pytest.approx(4.183697, rel=1e-6)
    assert base.z_base_ohm == pytest.approx(1.9044)
    assert base.y_base_siemens == pytest.approx(1 / 1.9044)


def test_ohm_to_per_unit() -> None:
    base = BaseQuantities(100.0, 13.8)
    assert ohm_to_pu(0.19044 + 0.0j, base) == pytest.approx(0.1 + 0.0j)


def test_per_unit_to_ohm() -> None:
    base = BaseQuantities(100.0, 13.8)
    assert pu_to_ohm(0.1 + 0.2j, base) == pytest.approx(0.19044 + 0.38088j)


def test_round_trip_ohm_per_unit_ohm() -> None:
    base = BaseQuantities(100.0, 13.8)
    original = 0.23 + 0.71j
    assert pu_to_ohm(ohm_to_pu(original, base), base) == pytest.approx(original)


def test_convert_per_unit_base() -> None:
    old_base = BaseQuantities(50.0, 13.8)
    new_base = BaseQuantities(100.0, 13.8)
    assert convert_pu_base(0.1 + 0.0j, old_base, new_base) == pytest.approx(0.2 + 0.0j)


def test_convert_per_unit_base_accounts_for_voltage_change() -> None:
    old_base = BaseQuantities(100.0, 13.8)
    new_base = BaseQuantities(100.0, 69.0)
    expected = 0.1 * (13.8 / 69.0) ** 2
    assert convert_pu_base(0.1, old_base, new_base).real == pytest.approx(expected)


@pytest.mark.parametrize(
    "s_base,v_base",
    [(0.0, 13.8), (100.0, 0.0), (-1.0, 13.8), (100.0, float("inf"))],
)
def test_base_quantities_reject_invalid_values(s_base: float, v_base: float) -> None:
    with pytest.raises(ValueError):
        BaseQuantities(s_base, v_base)


def test_impedance_conversion_rejects_non_finite_values() -> None:
    base = BaseQuantities(100.0, 13.8)
    with pytest.raises(ValueError):
        ohm_to_pu(complex(float("inf"), 0.0), base)
