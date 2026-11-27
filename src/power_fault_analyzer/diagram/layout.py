"""Deterministic, presentation-only geometry primitives for engineering diagrams.

Coordinates are expressed in scene units. Electrical connectivity is deliberately
not inferred from geometry: callers must provide explicit terminal coordinates.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from math import cos, floor, isfinite, radians, sin


@dataclass(frozen=True, slots=True)
class Point:
    x: float
    y: float

    def __post_init__(self) -> None:
        if not isfinite(self.x) or not isfinite(self.y):
            raise ValueError("Point coordinates must be finite.")


@dataclass(frozen=True, slots=True)
class Rect:
    x: float
    y: float
    width: float
    height: float

    def __post_init__(self) -> None:
        if not all(isfinite(v) for v in (self.x, self.y, self.width, self.height)):
            raise ValueError("Rectangle values must be finite.")
        if self.width <= 0 or self.height <= 0:
            raise ValueError("Rectangle width and height must be positive.")

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height

    def intersects(self, other: Rect, clearance: float = 0.0) -> bool:
        return not (
            self.right + clearance <= other.x
            or other.right + clearance <= self.x
            or self.bottom + clearance <= other.y
            or other.bottom + clearance <= self.y
        )


class ElementMetrics(StrEnum):
    BUSBAR = "busbar"
    SOURCE = "source"
    GENERATOR = "generator"
    TRANSFORMER = "transformer"
    SWITCHING = "switching"
    PROTECTION = "protection"
    TERMINAL = "terminal"
    CONNECTION_NODE = "connection_node"
    LINE = "line"
    CIRCUIT_BREAKER = "circuit_breaker"
    DISCONNECTOR = "disconnector"
    EARTHING_SWITCH = "earthing_switch"
    LOAD = "load"
    CAPACITOR = "capacitor"
    REACTOR = "reactor"
    COMPENSATION = "compensation"


@dataclass(frozen=True, slots=True)
class SymbolMetrics:
    width: float
    height: float
    minimum_clearance: float


# Baseline drawing dimensions; not physical equipment dimensions or IEC symbol claims.
SYMBOL_METRICS: dict[ElementMetrics, SymbolMetrics] = {
    ElementMetrics.BUSBAR: SymbolMetrics(600.0, 8.0, 36.0),
    ElementMetrics.SOURCE: SymbolMetrics(48.0, 48.0, 32.0),
    ElementMetrics.GENERATOR: SymbolMetrics(48.0, 48.0, 32.0),
    ElementMetrics.TRANSFORMER: SymbolMetrics(64.0, 92.0, 36.0),
    ElementMetrics.SWITCHING: SymbolMetrics(24.0, 54.0, 24.0),
    ElementMetrics.PROTECTION: SymbolMetrics(32.0, 32.0, 20.0),
    ElementMetrics.TERMINAL: SymbolMetrics(8.0, 8.0, 12.0),
    ElementMetrics.CONNECTION_NODE: SymbolMetrics(12.0, 12.0, 16.0),
    ElementMetrics.LINE: SymbolMetrics(44.0, 18.0, 28.0),
    ElementMetrics.CIRCUIT_BREAKER: SymbolMetrics(44.0, 28.0, 28.0),
    ElementMetrics.DISCONNECTOR: SymbolMetrics(44.0, 28.0, 28.0),
    ElementMetrics.EARTHING_SWITCH: SymbolMetrics(44.0, 32.0, 28.0),
    ElementMetrics.LOAD: SymbolMetrics(52.0, 52.0, 32.0),
    ElementMetrics.CAPACITOR: SymbolMetrics(48.0, 56.0, 32.0),
    ElementMetrics.REACTOR: SymbolMetrics(52.0, 64.0, 32.0),
    ElementMetrics.COMPENSATION: SymbolMetrics(52.0, 52.0, 32.0),
}


@dataclass(frozen=True, slots=True)
class DiagramElement:
    identifier: str
    family: ElementMetrics
    center: Point

    @property
    def bounds(self) -> Rect:
        metric = SYMBOL_METRICS[self.family]
        return Rect(
            self.center.x - metric.width / 2,
            self.center.y - metric.height / 2,
            metric.width,
            metric.height,
        )


@dataclass(frozen=True, slots=True)
class LabelPlacement:
    text: str
    bounds: Rect
    anchor: Point
    side: str


def snap_value(value: float, spacing: float) -> float:
    if not isfinite(value) or not isfinite(spacing) or spacing <= 0:
        raise ValueError("Snap value and spacing must be finite; spacing must be positive.")
    return floor(value / spacing + 0.5) * spacing


def snap_point(point: Point, spacing: float) -> Point:
    return Point(snap_value(point.x, spacing), snap_value(point.y, spacing))


def rotated_rect_bounds(
    center: Point, width: float, height: float, rotation_deg: float
) -> Rect:
    """Return the axis-aligned envelope of a rotated symbol rectangle."""
    if (not isfinite(width) or not isfinite(height) or width <= 0.0 or height <= 0.0
            or not isfinite(rotation_deg)):
        raise ValueError("Rotated rectangle dimensions and angle must be finite and positive.")
    angle = radians(rotation_deg % 360.0)
    rotated_width = abs(width * cos(angle)) + abs(height * sin(angle))
    rotated_height = abs(width * sin(angle)) + abs(height * cos(angle))
    return Rect(
        center.x - rotated_width / 2.0,
        center.y - rotated_height / 2.0,
        max(rotated_width, 0.1),
        max(rotated_height, 0.1),
    )


def segment_bounds(first: Point, second: Point, clearance: float = 6.0) -> Rect:
    """Return a collision envelope for a rendered conductor segment."""
    if not isfinite(clearance) or clearance <= 0.0:
        raise ValueError("Segment clearance must be finite and positive.")
    left = min(first.x, second.x) - clearance / 2.0
    top = min(first.y, second.y) - clearance / 2.0
    return Rect(
        left, top, max(clearance, abs(second.x - first.x) + clearance),
        max(clearance, abs(second.y - first.y) + clearance),
    )


def anchored_label_bounds(
    position: Point, width: float, height: float, anchor: str
) -> Rect:
    """Return a text envelope using SVG/Qt's shared baseline anchor convention."""
    if (not isfinite(width) or not isfinite(height) or width <= 0.0 or height <= 0.0
            or anchor not in {"start", "middle", "end"}):
        raise ValueError("Label dimensions and anchor must be valid.")
    left = (
        position.x - width / 2.0 if anchor == "middle"
        else position.x - width if anchor == "end"
        else position.x
    )
    return Rect(left, position.y - height, width, height)

def select_straight_bus_taps(
    terminal_axis_offsets: Sequence[tuple[str, float]],
    *,
    minimum_separation: float = 18.0,
    tolerance: float = 1e-7,
) -> frozenset[str]:
    """Select all bus taps for straight drops only when none would collide.

    A selected bus group may use the orthogonal projection of each terminal
    onto the bus axis, producing straight bus-normal conductors. If any pair
    of projected tap positions is too close, the caller must retain the
    precomputed bay offsets for the entire bus group. This all-or-none policy
    prevents a direct tap from colliding with a neighboring reserved bay.
    """
    if (not isfinite(minimum_separation) or minimum_separation <= 0
            or not isfinite(tolerance) or tolerance <= 0):
        raise ValueError("Tap separation and tolerance must be finite and positive.")
    identifiers: set[str] = set()
    normalized: list[tuple[str, float]] = []
    for identifier, offset in terminal_axis_offsets:
        if not identifier or identifier in identifiers:
            raise ValueError("Terminal tap identifiers must be non-empty and unique.")
        if not isfinite(offset):
            raise ValueError("Terminal tap offsets must be finite.")
        identifiers.add(identifier)
        normalized.append((identifier, float(offset)))

    for index, (_, offset) in enumerate(normalized):
        if any(
            abs(offset - other_offset) < minimum_separation - tolerance
            for _, other_offset in normalized[index + 1 :]
        ):
            return frozenset()
    return frozenset(identifiers)


def orthogonal_route(
    start: Point, end: Point, *, horizontal_first: bool = True
) -> tuple[Point, ...]:
    """Return a deterministic Manhattan route between explicit terminal positions."""
    if start == end:
        return (start,)
    if horizontal_first:
        bend = Point(end.x, start.y)
    else:
        bend = Point(start.x, end.y)
    if bend == start or bend == end:
        return (start, end)
    return (start, bend, end)


def perpendicular_bay_route(
    start: Point,
    end: Point,
    bus_orientation_deg: float = 0.0,
    *,
    clearance: float = 18.0,
    minimum_stub: float = 6.0,
    tolerance: float = 1e-7,
) -> tuple[Point, ...]:
    """Return a minimum-length orthogonal bay route with normal end approaches.

    The first and last legs are constrained to be perpendicular to the busbar.
    If the endpoints share a bus-normal lane, the mathematically shortest route
    is one straight segment; no duplicate/collinear waypoints are emitted.
    Otherwise a single bus-parallel middle leg joins the two mandatory normal
    legs, attaining the Manhattan lower bound whenever the endpoints have a
    non-zero normal separation.

    When both endpoints lie exactly on the bus axis, a small ``minimum_stub``
    offset is used on the positive normal side so the route still visibly
    leaves and approaches the bus perpendicularly.  That degenerate case is
    shortest subject to this non-zero lead-in constraint.
    """
    if not isfinite(bus_orientation_deg):
        raise ValueError("bus_orientation_deg must be finite.")
    if (not isfinite(clearance) or not isfinite(minimum_stub)
            or clearance < 0 or minimum_stub < 0 or tolerance <= 0):
        raise ValueError("Route clearances must be finite and non-negative; tolerance must be positive.")

    dx, dy = end.x - start.x, end.y - start.y
    if abs(dx) <= tolerance and abs(dy) <= tolerance:
        return (start,)

    angle = radians(bus_orientation_deg)
    axis_x, axis_y = cos(angle), sin(angle)
    normal_x, normal_y = -axis_y, axis_x
    tangential = dx * axis_x + dy * axis_y
    normal_distance = dx * normal_x + dy * normal_y

    # Collinear points on the normal axis need no bend at all.  Emitting the
    # direct two-point path also avoids QPainterPath retaining redundant
    # collinear waypoints as extra elements.
    if abs(tangential) <= tolerance:
        return (start, end)

    if abs(normal_distance) <= tolerance:
        direction = 1.0
        stub = minimum_stub
        lane_offset = direction * stub
    else:
        direction = 1.0 if normal_distance > 0.0 else -1.0
        stub = min(clearance, abs(normal_distance) / 2.0)
        lane_offset = normal_distance - direction * stub

    first_corner = Point(
        start.x + normal_x * lane_offset,
        start.y + normal_y * lane_offset,
    )
    second_corner = Point(
        end.x - normal_x * direction * stub,
        end.y - normal_y * direction * stub,
    )

    # Drop repeated points and any intermediate point that lies on the same
    # forward straight segment.  This makes route element count reflect actual
    # geometric bends, rather than construction artefacts.
    candidates = (start, first_corner, second_corner, end)
    result: list[Point] = []
    for point in candidates:
        if result and (abs(point.x - result[-1].x) <= tolerance
                       and abs(point.y - result[-1].y) <= tolerance):
            continue
        while len(result) >= 2:
            first, middle = result[-2], result[-1]
            ax, ay = middle.x - first.x, middle.y - first.y
            bx, by = point.x - middle.x, point.y - middle.y
            cross = ax * by - ay * bx
            dot = ax * bx + ay * by
            if abs(cross) <= tolerance and dot >= -tolerance:
                result.pop()
            else:
                break
        result.append(point)
    return tuple(result)


def layout_rows(
    elements: Sequence[DiagramElement], *, origin: Point = Point(0.0, 0.0),
    columns: int = 4, horizontal_gap: float = 80.0, vertical_gap: float = 100.0,
    grid_spacing: float = 20.0,
) -> tuple[DiagramElement, ...]:
    """Arrange elements deterministically in rows using family envelopes and clearances."""
    if columns < 1 or horizontal_gap < 0 or vertical_gap < 0:
        raise ValueError("columns must be positive and gaps cannot be negative.")
    if grid_spacing <= 0:
        raise ValueError("grid_spacing must be positive.")
    result: list[DiagramElement] = []
    row_heights: list[float] = []
    row_widths: list[float] = []
    for start in range(0, len(elements), columns):
        row = elements[start : start + columns]
        row_heights.append(max(SYMBOL_METRICS[item.family].height for item in row))
        row_widths.append(sum(SYMBOL_METRICS[item.family].width for item in row)
                          + horizontal_gap * max(0, len(row) - 1))
    y = origin.y
    for row_index, start in enumerate(range(0, len(elements), columns)):
        row = elements[start : start + columns]
        x = origin.x
        for item in row:
            metric = SYMBOL_METRICS[item.family]
            center = snap_point(
                Point(x + metric.width / 2, y + row_heights[row_index] / 2),
                grid_spacing,
            )
            result.append(DiagramElement(item.identifier, item.family, center))
            x += metric.width + horizontal_gap
        y += row_heights[row_index] + vertical_gap
    return tuple(result)


def align_group(
    elements: Iterable[DiagramElement], *, axis: str, coordinate: float
) -> tuple[DiagramElement, ...]:
    if axis not in {"x", "y"} or not isfinite(coordinate):
        raise ValueError("axis must be 'x' or 'y' and coordinate must be finite.")
    return tuple(
        DiagramElement(item.identifier, item.family,
                       Point(coordinate, item.center.y) if axis == "x"
                       else Point(item.center.x, coordinate))
        for item in elements
    )


def avoid_label_collisions(
    text: str, anchor: Point, width: float, height: float,
    obstacles: Sequence[Rect], *, gap: float = 8.0, max_steps: int = 12,
) -> LabelPlacement:
    """Place a label using deterministic candidate positions around its anchor."""
    if not text.strip() or width <= 0 or height <= 0 or gap < 0 or max_steps < 1:
        raise ValueError("Label text, dimensions, gap and max_steps must be valid.")
    offsets = (
        (0.0, -height - gap, "top"), (0.0, gap, "bottom"),
        (gap, -height / 2, "right"), (-width - gap, -height / 2, "left"),
    )
    for step in range(max_steps):
        dx, dy, side = offsets[step % len(offsets)]
        ring = step // len(offsets)
        x = anchor.x + dx + (ring * (width + gap) if side in {"left", "right"} else 0.0)
        y = anchor.y + dy - (ring * (height + gap) if side in {"top", "bottom"} else 0.0)
        bounds = Rect(x, y, width, height)
        if not any(bounds.intersects(obstacle, clearance=gap) for obstacle in obstacles):
            return LabelPlacement(text, bounds, anchor, side)
    raise ValueError(
        f"Could not place label {text!r} without a collision "
        f"after {max_steps} candidates."
    )
