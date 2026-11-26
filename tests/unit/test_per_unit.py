import pytest

from power_fault_analyzer.electrical.per_unit import (
    BaseQuantities,
    convert_pu_base,
    ohm_to_pu,
    pu_to_ohm,
)


def test_base_quantities():
    base = BaseQuantities(
        s_base_mva=100.0,
        v_base_kv=13.8,
    )

    assert base.i_base_ka == pytest.approx(4.183697)
    assert base.z_base_ohm == pytest.approx(1.9044)


def test_ohm_to_pu():
    base = BaseQuantities(100.0, 13.8)

    result = ohm_to_pu(0.19044 + 0.0j, base)

    assert result.real == pytest.approx(0.1)
    assert result.imag == pytest.approx(0.0)


def test_pu_to_ohm():
    base = BaseQuantities(100.0, 13.8)

    result = pu_to_ohm(0.1 + 0.2j, base)

    assert result.real == pytest.approx(0.19044)
    assert result.imag == pytest.approx(0.38088)


def test_convert_pu_base():
    old_base = BaseQuantities(50.0, 13.8)
    new_base = BaseQuantities(100.0, 13.8)

    result = convert_pu_base(0.1 + 0j, old_base, new_base)

    assert result.real == pytest.approx(0.2)
    assert result.imag == pytest.approx(0.0)


def test_invalid_base():
    with pytest.raises(ValueError):
        BaseQuantities(0.0, 13.8)


def test_invalid_impedance():
    base = BaseQuantities(100.0, 13.8)

    with pytest.raises(ValueError):
        ohm_to_pu(complex(float("inf"), 0), base)
