from uuid import uuid4

import pytest

from power_fault_analyzer.domain.entities.bus import Bus
from power_fault_analyzer.domain.value_objects.voltage import (
    Voltage,
    VoltageReference,
)


def test_bus_accepts_line_to_line_nominal_voltage() -> None:
    bus = Bus(name="BUS-01", nominal_voltage=Voltage.from_kv(13.8))
    assert bus.name == "BUS-01"
    assert bus.nominal_voltage.value_kv == pytest.approx(13.8)
    assert bus.id is not None


def test_bus_normalizes_name() -> None:
    bus = Bus(name="  BUS-01  ", nominal_voltage=Voltage.from_kv(13.8))
    assert bus.name == "BUS-01"


def test_bus_rejects_empty_name() -> None:
    with pytest.raises(ValueError):
        Bus(name="  ", nominal_voltage=Voltage.from_kv(13.8))


def test_bus_rejects_non_uuid_identity() -> None:
    with pytest.raises(TypeError):
        Bus(
            name="BUS-01",
            nominal_voltage=Voltage.from_kv(13.8),
            id="bad",  # type: ignore[arg-type]
        )


def test_bus_rejects_phase_to_neutral_nominal_voltage() -> None:
    voltage = Voltage.from_kv(7.967, VoltageReference.PHASE_TO_NEUTRAL)
    with pytest.raises(ValueError, match="line-to-line"):
        Bus(name="BUS-01", nominal_voltage=voltage)


def test_bus_identity_is_preserved() -> None:
    bus_id = uuid4()
    bus = Bus(name="BUS-01", nominal_voltage=Voltage.from_kv(13.8), id=bus_id)
    assert bus.id == bus_id
