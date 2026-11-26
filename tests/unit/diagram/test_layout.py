from __future__ import annotations

from itertools import pairwise

import pytest

from power_fault_analyzer.diagram.layout import (
    DiagramElement,
    ElementMetrics,
    Point,
    Rect,
    align_group,
    avoid_label_collisions,
    layout_rows,
    orthogonal_route,
    perpendicular_bay_route,
    select_straight_bus_taps,
    snap_point,
)


def test_snap_point_uses_configured_grid() -> None:
    assert snap_point(Point(31.0, 49.0), 20.0) == Point(40.0, 40.0)


def test_orthogonal_route_preserves_explicit_terminal_endpoints() -> None:
    route = orthogonal_route(Point(10, 20), Point(90, 80))
    assert route == (Point(10, 20), Point(90, 20), Point(90, 80))
    assert all(a.x == b.x or a.y == b.y for a, b in pairwise(route))


def test_layout_rows_is_deterministic_and_snapped() -> None:
    items = (
        DiagramElement("B1", ElementMetrics.BUSBAR, Point(0, 0)),
        DiagramElement("S1", ElementMetrics.SOURCE, Point(0, 0)),
        DiagramElement("T1", ElementMetrics.TRANSFORMER, Point(0, 0)),
    )
    first = layout_rows(items, columns=2, grid_spacing=10)
    assert first == layout_rows(items, columns=2, grid_spacing=10)
    assert all(item.center.x % 10 == 0 and item.center.y % 10 == 0 for item in first)
    assert first[0].bounds.right < first[1].bounds.x
    assert first[2].center.y > first[0].center.y


def test_align_group_changes_only_requested_axis() -> None:
    items = (
        DiagramElement("S1", ElementMetrics.SOURCE, Point(10, 20)),
        DiagramElement("S2", ElementMetrics.SOURCE, Point(40, 80)),
    )
    aligned = align_group(items, axis="x", coordinate=100)
    assert [item.center for item in aligned] == [Point(100, 20), Point(100, 80)]


def test_label_placement_avoids_symbol_obstacle() -> None:
    obstacle = Rect(0, 0, 80, 40)
    placement = avoid_label_collisions("BUS-101", Point(40, 20), 60, 14, [obstacle])
    assert not placement.bounds.intersects(obstacle, clearance=8)
    assert placement.anchor == Point(40, 20)


def test_invalid_geometry_is_rejected() -> None:
    with pytest.raises(ValueError):
        snap_point(Point(1, 2), 0)
    with pytest.raises(ValueError):
        Rect(0, 0, -1, 2)


@pytest.mark.parametrize(
    ("offsets", "expected"),
    [
        ((("T1", 12.0),), {"T1"}),
        ((("T1", 0.0), ("T2", 40.0)), {"T1", "T2"}),
        ((("T1", 0.0), ("T2", 12.0)), set()),
        ((("T1", 0.0), ("T2", 12.0), ("T3", 50.0)), set()),
    ],
)
def test_straight_bus_taps_are_selected_only_without_terminal_collisions(offsets, expected):
    assert select_straight_bus_taps(offsets, minimum_separation=18.0) == frozenset(expected)


def test_straight_bus_tap_rejects_duplicate_ids_and_invalid_offsets():
    with pytest.raises(ValueError, match="unique"):
        select_straight_bus_taps((("T1", 0.0), ("T1", 40.0)))
    with pytest.raises(ValueError, match="finite"):
        select_straight_bus_taps((("T1", float("inf")),))


def test_single_bus_drop_is_one_straight_segment_when_terminal_is_projected_to_bus():
    bus_tap = Point(812.0, 612.0)
    equipment_terminal = Point(812.0, 496.0)
    route = perpendicular_bay_route(bus_tap, equipment_terminal, 0.0)
    assert route == (bus_tap, equipment_terminal)


def test_vertical_bus_also_allows_a_straight_perpendicular_drop():
    bus_tap = Point(100.0, 200.0)
    equipment_terminal = Point(220.0, 200.0)
    assert perpendicular_bay_route(bus_tap, equipment_terminal, 90.0) == (
        bus_tap,
        equipment_terminal,
    )
