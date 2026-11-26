from __future__ import annotations

from uuid import UUID

from power_fault_analyzer.diagram.layout import Point
from power_fault_analyzer.diagram.model_projection import (
    EngineeringBus,
    _bus_bounds,
    _equipment_center_for_single_terminal,
)


def test_vertical_bus_uses_horizontal_envelope_for_single_terminal_equipment():
    center = Point(100.0, 200.0)
    bus = EngineeringBus(
        bus_id=UUID("00000000-0000-0000-0000-000000000001"),
        name="BUS-V",
        nominal_voltage_kv=13.8,
        bounds=_bus_bounds(center, 90.0, 240.0),
        center=center,
        orientation_deg=90.0,
    )
    tap = Point(100.0, 160.0)
    half_width = bus.bounds.width / 2.0

    source = _equipment_center_for_single_terminal("source", bus, tap)
    load = _equipment_center_for_single_terminal("load", bus, tap)

    assert source == Point(center.x - half_width - 70.0, tap.y)
    assert load == Point(center.x + half_width + 70.0, tap.y)


def test_horizontal_bus_keeps_single_terminal_equipment_above_and_below():
    center = Point(100.0, 200.0)
    bus = EngineeringBus(
        bus_id=UUID("00000000-0000-0000-0000-000000000002"),
        name="BUS-H",
        nominal_voltage_kv=13.8,
        bounds=_bus_bounds(center, 0.0, 240.0),
        center=center,
        orientation_deg=0.0,
    )
    tap = Point(130.0, center.y)

    source = _equipment_center_for_single_terminal("source", bus, tap)
    load = _equipment_center_for_single_terminal("load", bus, tap)

    assert source == Point(tap.x, center.y - 72.0)
    assert load == Point(tap.x, center.y + 72.0)
