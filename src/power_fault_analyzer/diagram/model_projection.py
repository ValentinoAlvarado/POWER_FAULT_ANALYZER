"""Canonical electrical-model projection and compact engineering composition.

The physical Network aggregate remains authoritative for equipment, terminals and
connections.  This module computes only presentation geometry and independent
annotation placements; it never changes the electrical model or infers topology
from intersections in the drawing.
"""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from itertools import pairwise
from math import cos, hypot, radians, sin
from uuid import NAMESPACE_URL, UUID, uuid5

from power_fault_analyzer.application.use_cases.network_workspace import (
    DiagramLabelPlacement,
    NetworkWorkspace,
)
from power_fault_analyzer.domain.aggregates.network import Network
from power_fault_analyzer.equipment.interfaces.unresolved_branch import (
    UnresolvedTwoTerminalEquipment,
)
from power_fault_analyzer.equipment.interfaces.unresolved_equipment import (
    UnresolvedEquipmentInterface,
)
from power_fault_analyzer.equipment.interfaces.unresolved_single_terminal import (
    UnresolvedSingleTerminalEquipment,
)
from power_fault_analyzer.equipment.sources.equivalent_source import EquivalentSource
from power_fault_analyzer.equipment.sources.synchronous_generator import SynchronousGenerator
from power_fault_analyzer.equipment.switching.switching_device import SwitchingDevice
from power_fault_analyzer.equipment.transformers.two_winding_transformer import (
    TwoWindingTransformer,
)
from power_fault_analyzer.equipment.transmission.line import Line

from .layout import Point, Rect, perpendicular_bay_route, snap_point
from .symbol_catalog import get_symbol_definition
from .topology_layout import BayLaneRequest, layout_bay_lanes


@dataclass(frozen=True, slots=True)
class EngineeringSymbol:
    equipment_id: UUID
    name: str
    family: str
    center: Point
    width: float
    height: float
    terminal_ids: tuple[UUID, ...]
    terminal_points: tuple[Point, ...]
    state: str | None = None
    orientation_deg: float = 0.0
    layer: str = "equipment"
    symbol_id: str = ""
    terminal_designations: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class EngineeringBus:
    bus_id: UUID
    name: str
    nominal_voltage_kv: float
    bounds: Rect
    center: Point
    orientation_deg: float = 0.0
    layer: str = "conductors"
    kind: str = "busbar"

    @property
    def length(self) -> float:
        return self.bounds.width if abs(self.orientation_deg % 180.0) < 1e-6 else self.bounds.height


@dataclass(frozen=True, slots=True)
class EngineeringConductor:
    terminal_id: UUID
    bus_id: UUID
    points: tuple[Point, ...]
    layer: str = "conductors"

    @property
    def bus_point(self) -> Point:
        return self.points[0]


@dataclass(frozen=True, slots=True)
class EngineeringLabel:
    owner_id: UUID | None
    text: str
    position: Point
    anchor: str = "middle"
    label_id: UUID | None = None
    font_family: str = "Segoe UI"
    size_pt: float = 7.5
    weight: str = "normal"
    color: str = "#172033"
    rotation_deg: float = 0.0
    visible: bool = True
    layer: str = "annotations"
    priority: int = 50
    unit: str | None = None
    number_format: str | None = None


@dataclass(frozen=True, slots=True)
class DiagramDocument:
    network_id: UUID
    network_name: str
    buses: tuple[EngineeringBus, ...]
    symbols: tuple[EngineeringSymbol, ...]
    conductors: tuple[EngineeringConductor, ...]
    labels: tuple[EngineeringLabel, ...]
    diagnostics: tuple[str, ...]

    @property
    def equipment_ids(self) -> frozenset[UUID]:
        return frozenset(item.equipment_id for item in self.symbols)

    @property
    def terminal_ids(self) -> frozenset[UUID]:
        return frozenset(terminal for item in self.symbols for terminal in item.terminal_ids)

    @property
    def connection_pairs(self) -> frozenset[tuple[UUID, UUID]]:
        return frozenset((item.terminal_id, item.bus_id) for item in self.conductors)


class DiagramProjectionError(ValueError):
    """Canonical model cannot be projected without losing topology."""


_BUS_MIN_LENGTH = 160.0
_BUS_LENGTH_PER_EXTRA_TERMINAL = 36.0
_BUS_MAX_LENGTH = 280.0
_BUS_THICKNESS = 6.0
_PATH_BUS_SPACING = 280.0
_PATH_CENTER_Y = 420.0
LABEL_SCENE_UNITS_PER_PT = 2.8
_EQUIPMENT_LABEL_OWNER_RADIUS = 74.0
_EQUIPMENT_LABEL_SEARCH_STEP = 2.0
_EQUIPMENT_LABEL_MAX_TANGENT_SHIFT = 48.0
_EQUIPMENT_LABEL_MIN_NORMAL_ADJUSTMENT = -16.0
_EQUIPMENT_LABEL_MAX_NORMAL_ADJUSTMENT = 24.0


def _equipment_family(equipment) -> tuple[str, str | None]:
    if isinstance(equipment, EquivalentSource):
        partial = (
            equipment.equivalent.negative.status.value != "AVAILABLE"
            or equipment.equivalent.zero.status.value != "AVAILABLE"
        )
        return "source", "partial-data" if partial else None
    if isinstance(equipment, SynchronousGenerator):
        return "generator", None
    if isinstance(equipment, TwoWindingTransformer):
        return "transformer", None
    if isinstance(equipment, SwitchingDevice):
        return equipment.device_kind.value, equipment.position.value
    if isinstance(equipment, Line):
        return "line", None
    if isinstance(equipment, UnresolvedSingleTerminalEquipment):
        kind = equipment.equipment_kind.casefold().replace("-", "_").replace(" ", "_")
        equipment_family = getattr(equipment.family, "value", str(equipment.family)).casefold()
        statuses = tuple(item.status.value for item in equipment.parameters)
        has_confirmed = any(item not in {"UNRESOLVED", "CONFLICTING"} for item in statuses)
        has_pending = any(item in {"UNRESOLVED", "CONFLICTING"} for item in statuses)
        state = "partial-data" if has_confirmed and has_pending else "unresolved" if has_pending else None
        if kind in {"load", "static_load", "demand", "consumer"} or equipment_family == "load":
            return "load", state
        if "capacitor" in kind or kind in {"cap_bank", "capacitor_bank"}:
            return "capacitor", state
        if "reactor" in kind or kind in {"inductor", "shunt_inductor"}:
            return "reactor", state
        if equipment_family == "compensation" or "compens" in kind:
            return "compensation", state
        if kind in {"generator", "synchronous_generator"} or equipment_family == "generator":
            return "generator", state
        if kind in {"source", "external_grid", "grid_equivalent"} or equipment_family == "source":
            return "source", state
        return "generic", state

    if isinstance(equipment, (UnresolvedTwoTerminalEquipment, UnresolvedEquipmentInterface)):
        kind = equipment.equipment_kind if isinstance(equipment, UnresolvedTwoTerminalEquipment) else (
            "line" if equipment.interface_kind.value == "transmission_line" else "transformer"
        )
        normalized = kind.casefold().replace("-", "_").replace(" ", "_")
        if normalized in {"line", "transmission_line", "overhead_line", "underground_cable"}:
            return "line", "unresolved"
        if normalized in {"transformer", "two_winding_transformer", "power_transformer"}:
            return "transformer", "unresolved"
        if "capacitor" in normalized:
            return "capacitor", "unresolved"
        if "reactor" in normalized:
            return "reactor", "unresolved"
        if "compens" in normalized:
            return "compensation", "unresolved"
        if normalized in {"load", "static_load", "demand", "consumer"}:
            return "load", "unresolved"
        return "generic", "unresolved"
    raise DiagramProjectionError(
        f"Equipment {equipment.name!r} ({type(equipment).__name__}) has no documented "
        "diagram symbol mapping. It is not silently omitted."
    )


def _connected_bus_ids(network: Network) -> dict[UUID, UUID]:
    return {item.terminal_id: item.bus_id for item in network.connections}


def _topology(network: Network):
    """Return bus adjacency and equipment references from explicit terminal links."""
    connected = _connected_bus_ids(network)
    adjacency: dict[UUID, set[UUID]] = {bus.id: set() for bus in network.buses}
    equipment_by_pair: dict[frozenset[UUID], list] = defaultdict(list)
    shunts: dict[UUID, list] = defaultdict(list)
    for equipment in network.equipment:
        terminal_buses = [connected.get(item.id) for item in equipment.terminals]
        if any(item is None for item in terminal_buses):
            continue
        if len(terminal_buses) == 1:
            shunts[terminal_buses[0]].append(equipment)
        elif len(terminal_buses) == 2:
            first, second = terminal_buses
            if first != second:
                adjacency[first].add(second)
                adjacency[second].add(first)
                equipment_by_pair[frozenset((first, second))].append(equipment)
    return adjacency, equipment_by_pair, shunts


def _source_priority(network: Network, shunts: dict[UUID, list]) -> dict[UUID, int]:
    priority: dict[UUID, int] = {}
    for bus_id, equipment_items in shunts.items():
        for equipment in equipment_items:
            family, _ = _equipment_family(equipment)
            rank = 0 if family == "source" else 1 if family == "generator" else 2
            priority[bus_id] = min(priority.get(bus_id, 9), rank)
    return priority


def _path_order(network: Network, adjacency: dict[UUID, set[UUID]], shunts: dict[UUID, list]):
    bus_order = {bus.id: index for index, bus in enumerate(network.buses)}
    if not network.buses:
        return None
    if len(network.buses) == 1:
        return [network.buses[0].id]
    edges = sum(len(items) for items in adjacency.values()) // 2
    if edges != len(network.buses) - 1 or any(len(items) > 2 for items in adjacency.values()):
        return None
    visited: set[UUID] = set()
    components: list[list[UUID]] = []
    for bus in network.buses:
        if bus.id in visited:
            continue
        queue = deque([bus.id])
        visited.add(bus.id)
        component = []
        while queue:
            current = queue.popleft()
            component.append(current)
            for neighbor in sorted(adjacency[current], key=lambda item: bus_order[item]):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
        components.append(component)
    if len(components) != 1:
        return None
    endpoints = [item for item in components[0] if len(adjacency[item]) <= 1]
    source_priority = _source_priority(network, shunts)
    start = min(endpoints, key=lambda item: (source_priority.get(item, 9), bus_order[item]))
    ordered = [start]
    previous = None
    current = start
    while True:
        candidates = [item for item in adjacency[current] if item != previous]
        if not candidates:
            break
        following = min(candidates, key=lambda item: bus_order[item])
        ordered.append(following)
        previous, current = current, following
    return ordered


def _busbar_length(terminal_count: int, bay_spacing: float = 180.0) -> float:
    """Size a busbar from its explicit terminal incidence and label envelope."""
    if terminal_count < 0:
        raise ValueError("terminal_count cannot be negative")
    if bay_spacing <= 0.0:
        raise ValueError("bay_spacing must be positive")
    return 220.0 + max(0, terminal_count - 1) * bay_spacing


def _automatic_bus_layout(network: Network, grid: float):
    """Arrange explicit bus connectivity as a deterministic, spacious tree layout.

    The spanning forest is built only from terminal-to-bus connection records.
    Every bus receives a unique level; siblings are centered beneath their parent
    using subtree widths. Non-tree electrical links remain in the model and are
    routed as additional edges without changing the connectivity graph.
    """
    adjacency, _equipment_by_pair, shunts = _topology(network)
    terminal_counts: dict[UUID, int] = {bus.id: 0 for bus in network.buses}
    for connection in network.connections:
        terminal_counts[connection.bus_id] = terminal_counts.get(connection.bus_id, 0) + 1
    bus_order = {bus.id: index for index, bus in enumerate(network.buses)}
    source_priority = _source_priority(network, shunts)
    roots = sorted(network.buses, key=lambda bus: (source_priority.get(bus.id, 9), bus_order[bus.id]))
    children: dict[UUID, list[UUID]] = defaultdict(list)
    depth: dict[UUID, int] = {}
    component_roots: list[UUID] = []
    for root in roots:
        if root.id in depth:
            continue
        component_roots.append(root.id)
        depth[root.id] = 0
        queue = deque([root.id])
        while queue:
            current = queue.popleft()
            for neighbor in sorted(adjacency[current], key=lambda item: bus_order[item]):
                if neighbor in depth:
                    continue
                depth[neighbor] = depth[current] + 1
                children[current].append(neighbor)
                queue.append(neighbor)

    subtree_widths: dict[UUID, float] = {}
    branch_gap = 320.0
    minimum_subtree_width = 260.0

    def subtree_width(identifier: UUID) -> float:
        if identifier in subtree_widths:
            return subtree_widths[identifier]
        child_widths = [subtree_width(item) for item in children[identifier]]
        width = max(minimum_subtree_width, sum(child_widths) + branch_gap * max(0, len(child_widths) - 1))
        subtree_widths[identifier] = width
        return width

    positions: dict[UUID, Point] = {}
    orientations: dict[UUID, float] = {}
    lengths: dict[UUID, float] = {}
    cursor_x = 520.0
    top_y = 240.0
    level_pitch = 380.0

    def place_subtree(identifier: UUID, center_x: float) -> None:
        positions[identifier] = snap_point(Point(center_x, top_y + depth[identifier] * level_pitch), grid)
        orientations[identifier] = 0.0
        child_items = sorted(children[identifier], key=lambda item: bus_order[item])
        if not child_items:
            return
        total_width = sum(subtree_width(item) for item in child_items) + branch_gap * (len(child_items) - 1)
        left = center_x - total_width / 2.0
        for child in child_items:
            width = subtree_width(child)
            child_center = left + width / 2.0
            place_subtree(child, child_center)
            left += width + branch_gap

    for root in component_roots:
        width = subtree_width(root)
        place_subtree(root, cursor_x + width / 2.0)
        cursor_x += width + 620.0

    equipment_by_terminal = {
        terminal.id: equipment
        for equipment in network.equipment
        for terminal in equipment.terminals
    }
    for bus in network.buses:
        connected_names = [
            equipment_by_terminal[item.terminal_id].name
            for item in network.connections
            if item.bus_id == bus.id and item.terminal_id in equipment_by_terminal
        ]
        widest_label = max((_estimated_label_width(name) for name in connected_names), default=180.0)
        spacing = max(180.0, widest_label)
        lengths[bus.id] = _busbar_length(terminal_counts.get(bus.id, 0), spacing)
    return positions, orientations, lengths


def _estimated_label_width(text: str, size_pt: float = 9.0) -> float:
    return max(48.0, len(text) * size_pt * 0.54 * LABEL_SCENE_UNITS_PER_PT + 24.0)


def _automatic_equipment_layout(
    network: Network, buses: dict[UUID, EngineeringBus],
) -> dict[UUID, tuple[Point, float]]:
    """Allocate two-terminal equipment to non-overlapping topology-derived bay lanes."""
    vertical_requests: list[BayLaneRequest] = []
    horizontal_requests: list[BayLaneRequest] = []
    metadata: dict[str, tuple[UUID, float, float, float, float, float]] = {}
    connection_by_terminal = _connected_bus_ids(network)
    for equipment in network.equipment:
        terminals = tuple(equipment.terminals)
        if len(terminals) != 2:
            continue
        first_bus_id = connection_by_terminal.get(terminals[0].id)
        second_bus_id = connection_by_terminal.get(terminals[1].id)
        if first_bus_id not in buses or second_bus_id not in buses:
            continue
        first = buses[first_bus_id]
        second = buses[second_bus_id]
        family, _state = _equipment_family(equipment)
        definition = get_symbol_definition(family)
        label_width = _estimated_label_width(equipment.name)
        same_level = abs(second.center.y - first.center.y) < 1e-6
        request_id = str(equipment.id)
        if same_level:
            left = min(first.center.x, second.center.x)
            right = max(first.center.x, second.center.x)
            if right - left < 120.0:
                left -= 60.0
                right += 60.0
            start, end = left, right
            preferred = max(first.center.y, second.center.y) + 190.0
            width = max(definition.height + 32.0, 76.0)
            horizontal_requests.append(BayLaneRequest(request_id, start, end, preferred, width))
            metadata[request_id] = (equipment.id, (first.center.x + second.center.x) / 2.0,
                                    (first.center.y + second.center.y) / 2.0, 0.0,
                                    definition.width, definition.height)
        else:
            top = min(first.center.y, second.center.y)
            bottom = max(first.center.y, second.center.y)
            if bottom - top < 180.0:
                top -= 90.0
                bottom += 90.0
            preferred = (first.center.x + second.center.x) / 2.0
            width = definition.height + label_width + 32.0
            vertical_requests.append(BayLaneRequest(request_id, top, bottom, preferred, width))
            direction = 90.0 if second.center.y >= first.center.y else -90.0
            metadata[request_id] = (equipment.id, preferred, (first.center.y + second.center.y) / 2.0,
                                    direction, definition.width, definition.height)
    vertical_lanes = layout_bay_lanes(vertical_requests, gap=56.0, search_step=100.0)
    horizontal_lanes = layout_bay_lanes(horizontal_requests, gap=44.0, search_step=100.0)
    result: dict[UUID, tuple[Point, float]] = {}
    for request_id, (equipment_id, base_x, base_y, orientation, _width, _height) in metadata.items():
        if request_id in vertical_lanes:
            center = Point(vertical_lanes[request_id], base_y)
        else:
            center = Point(base_x, horizontal_lanes[request_id])
        result[equipment_id] = (center, orientation)
    return result

def _bus_bounds(center: Point, orientation: float, length: float) -> Rect:
    if abs(orientation % 180.0) < 1e-6:
        return Rect(center.x - length / 2.0, center.y - _BUS_THICKNESS / 2.0,
                    length, _BUS_THICKNESS)
    return Rect(center.x - _BUS_THICKNESS / 2.0, center.y - length / 2.0,
                _BUS_THICKNESS, length)


def _bus_tap(bus: EngineeringBus, target: Point) -> Point:
    """Nearest explicit tap on the finite busbar segment or point node."""
    if bus.kind == "connection_node":
        return bus.center
    orientation = bus.orientation_deg % 180.0
    if abs(orientation) < 1e-6:
        offset = max(-bus.bounds.width / 2.0,
                     min(bus.bounds.width / 2.0, target.x - bus.center.x))
        return Point(bus.center.x + offset, bus.center.y)
    offset = max(-bus.bounds.height / 2.0,
                 min(bus.bounds.height / 2.0, target.y - bus.center.y))
    return Point(bus.center.x, bus.center.y + offset)


def _transform_local(center: Point, local: tuple[float, float], angle_deg: float) -> Point:
    angle = radians(angle_deg)
    x, y = local
    return Point(center.x + x * cos(angle) - y * sin(angle),
                 center.y + x * sin(angle) + y * cos(angle))


def _label(
    owner_id: UUID | None, text: str, position: Point, *, anchor: str = "middle",
    size_pt: float = 7.5, weight: str = "normal", color: str = "#172033",
    priority: int = 50, role: str = "annotations", label_key: str = "label",
) -> EngineeringLabel:
    label_id = uuid5(NAMESPACE_URL, f"urn:pfa:diagram-label:{owner_id}:{label_key}")
    return EngineeringLabel(owner_id, text, position, anchor, label_id, "Segoe UI",
                             size_pt, weight, color, 0.0, True, role, priority)


def _user_label(label: DiagramLabelPlacement) -> EngineeringLabel:
    return EngineeringLabel(
        label.owner_id, label.text, Point(label.x, label.y), label.anchor,
        label.label_id, label.font_family, label.size_pt, label.weight,
        label.color, label.rotation_deg, label.visible, label.layer, label.priority,
        label.unit, label.number_format,
    )


def _layout_equipment_label(
    equipment_id: UUID, name: str, state: str | None, center: Point,
    width: float, height: float, orientation_deg: float, *, side: str = "above",
) -> tuple[EngineeringLabel, ...]:
    """Place equipment text close to its *rotated* symbol envelope.

    Using max(width, height) for every orientation left unnecessary gaps beside
    vertical bay equipment. The rotated half-extents keep labels close without
    placing them over the actual glyph.
    """
    angle = radians(orientation_deg)
    half_width = (abs(cos(angle)) * width + abs(sin(angle)) * height) / 2.0
    half_height = (abs(sin(angle)) * width + abs(cos(angle)) * height) / 2.0
    label_clearance = 10.0
    label_size_pt = 9.0
    label_height = _label_scene_height(label_size_pt)

    if side == "below":
        # EngineeringLabel.position is the text baseline, and its scene bounds
        # extend upward from that baseline. Add the full text height here so a
        # below-symbol label starts beyond the glyph envelope instead of
        # overlapping the symbol and being pushed sideways by the collision pass.
        label_anchor = Point(
            center.x,
            center.y + half_height + label_clearance + label_height,
        )
        anchor = "middle"
    elif side == "right":
        label_anchor = Point(center.x + half_width + label_clearance, center.y + 4.0)
        anchor = "start"
    elif side == "left":
        label_anchor = Point(center.x - half_width - label_clearance, center.y + 4.0)
        anchor = "end"
    elif abs(orientation_deg % 180.0) > 1e-6:
        label_anchor = Point(center.x + half_width + label_clearance, center.y + 4.0)
        anchor = "start"
    else:
        label_anchor = Point(center.x, center.y - half_height - label_clearance)
        anchor = "middle"
    if state == "unresolved":
        name = f"{name}†"
    elif state == "partial-data":
        name = f"{name}‡"
    return (_label(equipment_id, name, label_anchor, anchor=anchor,
                   size_pt=label_size_pt, weight="semibold", priority=20,
                   label_key="equipment-name"),)


def _equipment_center_for_single_terminal(
    family: str, bus: EngineeringBus, tap: Point, *, clearance: float | None = None,
) -> Point:
    """Place a one-terminal device directly above/below its reserved bus tap."""
    if abs(bus.orientation_deg % 180.0) < 1e-6:
        # A shunt bay occupies the adjacent vertical corridor.  Do not place it
        # beyond half the busbar length: doing so can overlap the next bus row.
        offset = 72.0 if clearance is None else clearance
        y = bus.center.y - offset if family == "source" else bus.center.y + offset
        return Point(tap.x, y)
    half_bus_extent_x = bus.bounds.width / 2.0
    offset = 70.0 if clearance is None else clearance
    x = (
        bus.center.x - half_bus_extent_x - offset
        if family == "source"
        else bus.center.x + half_bus_extent_x + offset
    )
    return Point(x, tap.y)


def _route_to_terminal(
    bus_point: Point, terminal: Point, bus: EngineeringBus,
) -> tuple[Point, ...]:
    """Project the shared minimum-length route under perpendicular bay constraints."""
    return perpendicular_bay_route(
        bus_point, terminal, bus.orientation_deg, clearance=18.0, minimum_stub=6.0,
    )


def _tap_point(bus: EngineeringBus, coordinate: float) -> Point:
    """Convert a scalar coordinate on a busbar axis into a scene point."""
    if bus.kind == "connection_node":
        return bus.center
    if abs(bus.orientation_deg % 180.0) < 1e-6:
        return Point(coordinate, bus.center.y)
    return Point(bus.center.x, coordinate)


def _available_bus_axis(bus: EngineeringBus) -> tuple[float, float, float]:
    """Return the usable scalar interval and center of a finite busbar or node."""
    if bus.kind == "connection_node":
        return bus.center.x, bus.center.x, bus.center.x
    if abs(bus.orientation_deg % 180.0) < 1e-6:
        low, high, center = bus.bounds.x + 10.0, bus.bounds.right - 10.0, bus.center.x
    else:
        low, high, center = bus.bounds.y + 10.0, bus.bounds.bottom - 10.0, bus.center.y
    if high < low:
        return center, center, center
    return low, high, center


def _choose_free_tap(
    bus: EngineeringBus, occupied: list[float], preferred: float,
    *, minimum_separation: float = 18.0,
) -> float:
    """Choose the nearest free position on a bar, relaxing only if necessary."""
    low, high, center = _available_bus_axis(bus)
    if high - low <= 1e-7:
        return center
    # A fine deterministic candidate lattice avoids endpoint bias while keeping
    # every tap inside the physical finite extent of the busbar.
    steps = max(1, int((high - low) // 4.0))
    candidates = [low + (high - low) * index / steps for index in range(steps + 1)]
    if not occupied:
        return min(candidates, key=lambda value: (abs(value - preferred), value))
    for separation in (minimum_separation, 36.0, 18.0, 8.0, 0.0):
        free = [value for value in candidates
                if all(abs(value - used) >= separation - 1e-7 for used in occupied)]
        if free:
            return min(free, key=lambda value: (abs(value - preferred), value))
    return max(candidates, key=lambda value: (min(abs(value - used) for used in occupied),
                                               -abs(value - preferred)))


def _terminal_bus_taps(
    network: Network, buses: dict[UUID, EngineeringBus],
    preferred_equipment_positions: dict[UUID, Point] | None = None,
) -> dict[UUID, Point]:
    """Allocate unique taps and align both ends of each bay on a shared lane.

    Two-terminal equipment receives one common X (or Y for vertical bars) at
    both connected buses whenever their finite extents overlap.  This makes
    default bay conductors straight and perpendicular instead of introducing
    needless horizontal jogs.  Shunt equipment is then placed over its own
    free tap.  All assignments come from canonical terminal-to-bus links.
    """
    preferred_equipment_positions = preferred_equipment_positions or {}
    equipment_by_terminal = {
        terminal.id: (equipment, terminal)
        for equipment in network.equipment
        for terminal in equipment.terminals
    }
    bus_by_terminal = {item.terminal_id: item.bus_id for item in network.connections}
    clearance_by_bus: dict[UUID, float] = defaultdict(lambda: 120.0)
    for connection in network.connections:
        equipment_pair = equipment_by_terminal.get(connection.terminal_id)
        if equipment_pair is not None:
            clearance_by_bus[connection.bus_id] = max(
                clearance_by_bus[connection.bus_id],
                _estimated_label_width(equipment_pair[0].name),
            )
    result: dict[UUID, Point] = {}
    occupied: dict[UUID, list[float]] = defaultdict(list)

    # Align two-terminal equipment to a single lane common to both finite bars.
    two_terminal = []
    for equipment in network.equipment:
        terminals = tuple(equipment.terminals)
        if len(terminals) != 2:
            continue
        first_bus_id = bus_by_terminal.get(terminals[0].id)
        second_bus_id = bus_by_terminal.get(terminals[1].id)
        if first_bus_id is None or second_bus_id is None or first_bus_id == second_bus_id:
            continue
        two_terminal.append((equipment, terminals, buses[first_bus_id], buses[second_bus_id]))

    for equipment, terminals, first_bus, second_bus in sorted(
        two_terminal, key=lambda item: (item[0].name.casefold(), str(item[0].id))
    ):
        first_horizontal = abs(first_bus.orientation_deg % 180.0) < 1e-6
        second_horizontal = abs(second_bus.orientation_deg % 180.0) < 1e-6
        if first_horizontal and second_horizontal:
            low = max(_available_bus_axis(first_bus)[0], _available_bus_axis(second_bus)[0])
            high = min(_available_bus_axis(first_bus)[1], _available_bus_axis(second_bus)[1])
            if high >= low:
                preferred_point = preferred_equipment_positions.get(equipment.id)
                preferred = preferred_point.x if preferred_point is not None else (low + high) / 2.0
                preferred = max(low, min(high, preferred))
                # The selected coordinate must be free on both buses. Search the
                # common interval by increasing distance from its center.
                steps = max(1, int((high - low) // 2.0))
                candidates = [low + (high - low) * index / steps for index in range(steps + 1)]
                candidates.sort(key=lambda value: (abs(value - preferred), value))
                # Keep separate bay equipment envelopes apart. The minimum
                # preferred lane separation is based on the widest built-in
                # symbols; only constrained/manual bar overlaps relax it.
                already_used = occupied[first_bus.bus_id] + occupied[second_bus.bus_id]
                minimum_separation = max(
                    clearance_by_bus[first_bus.bus_id],
                    clearance_by_bus[second_bus.bus_id],
                )
                chosen = next((value for value in candidates
                               if all(abs(value - used) >= minimum_separation - 1e-7
                                      for used in already_used)), None)
                if chosen is None:
                    chosen = next((value for value in candidates
                                   if all(abs(value - used) >= minimum_separation * 0.7 - 1e-7
                                          for used in already_used)), None)
                if chosen is None:
                    chosen = next((value for value in candidates
                                   if all(abs(value - used) >= 18.0 - 1e-7
                                          for used in already_used)), None)
                if chosen is not None:
                    result[terminals[0].id] = _tap_point(first_bus, chosen)
                    result[terminals[1].id] = _tap_point(second_bus, chosen)
                    occupied[first_bus.bus_id].append(chosen)
                    occupied[second_bus.bus_id].append(chosen)
        elif not first_horizontal and not second_horizontal:
            low = max(_available_bus_axis(first_bus)[0], _available_bus_axis(second_bus)[0])
            high = min(_available_bus_axis(first_bus)[1], _available_bus_axis(second_bus)[1])
            if high >= low:
                preferred = (low + high) / 2.0
                chosen = _choose_free_tap(first_bus, occupied[first_bus.bus_id], preferred)
                if low <= chosen <= high and all(abs(chosen - used) >= 8.0 for used in occupied[second_bus.bus_id]):
                    result[terminals[0].id] = _tap_point(first_bus, chosen)
                    result[terminals[1].id] = _tap_point(second_bus, chosen)
                    occupied[first_bus.bus_id].append(chosen)
                    occupied[second_bus.bus_id].append(chosen)

    # Allocate remaining terminals (one-terminal shunts, same-bus devices, or
    # non-overlapping manually placed bars) without reusing another terminal's tap.
    connections_by_bus: dict[UUID, list[tuple[object, object]]] = defaultdict(list)
    for connection in network.connections:
        pair = equipment_by_terminal.get(connection.terminal_id)
        if pair is None:
            raise DiagramProjectionError(
                f"Connection references unknown terminal {connection.terminal_id}."
            )
        connections_by_bus[connection.bus_id].append(pair)

    for bus_id, bus in buses.items():
        connected = connections_by_bus.get(bus_id, [])
        def bay_key(pair):
            equipment, terminal = pair
            family, _ = _equipment_family(equipment)
            rank = {"source": 0, "generator": 1}.get(family, 2)
            return rank, equipment.name.casefold(), terminal.designation.casefold()

        for equipment, terminal in sorted(connected, key=bay_key):
            if terminal.id in result:
                continue
            family, _ = _equipment_family(equipment)
            _low, _high, center = _available_bus_axis(bus)
            preferred_point = preferred_equipment_positions.get(equipment.id)
            if preferred_point is not None:
                preferred = preferred_point.x if abs(bus.orientation_deg % 180.0) < 1e-6 else preferred_point.y
            elif family == "source":
                preferred = center - bus.length * 0.30
            elif family == "generator":
                preferred = center + bus.length * 0.30
            else:
                preferred = center
            coordinate = _choose_free_tap(
                bus, occupied[bus_id], preferred, minimum_separation=clearance_by_bus[bus_id]
            )
            result[terminal.id] = _tap_point(bus, coordinate)
            occupied[bus_id].append(coordinate)
    return result


def _label_scene_height(size_pt: float) -> float:
    """Return the annotation's vertical envelope in canonical scene units."""
    return max(12.0, size_pt * 1.25 * LABEL_SCENE_UNITS_PER_PT)


def _label_bounds(label: EngineeringLabel) -> Rect:
    # size_pt is a physical typographic size. Convert it to drawing-space
    # clearance using the default publication scale; the SVG renderer then
    # maps the exact point size to the chosen page dimensions.
    width = max(24.0, len(label.text) * label.size_pt * 0.54 * LABEL_SCENE_UNITS_PER_PT)
    height = _label_scene_height(label.size_pt)
    if label.anchor == "middle":
        left = label.position.x - width / 2.0
    elif label.anchor == "end":
        left = label.position.x - width
    else:
        left = label.position.x
    return Rect(left, label.position.y - height, width, height)


def _label_bounds_at(
    label: EngineeringLabel, position: Point, anchor: str,
) -> Rect:
    """Return the physical text envelope at a candidate baseline and anchor."""
    width = max(24.0, len(label.text) * label.size_pt * 0.54 * LABEL_SCENE_UNITS_PER_PT)
    height = _label_scene_height(label.size_pt)
    if anchor == "middle":
        left = position.x - width / 2.0
    elif anchor == "end":
        left = position.x - width
    else:
        left = position.x
    return Rect(left, position.y - height, width, height)


def _local_equipment_label_candidates(
    label: EngineeringLabel, symbol: EngineeringSymbol,
) -> tuple[tuple[Point, str], ...]:
    """Generate local label placements on all four sides of the owning symbol.

    The earlier search translated one fixed anchor. That cannot solve a label
    which is trapped between its own symbol and a vertical conductor: sliding
    left makes it hit the symbol, while sliding right keeps it on the conductor.
    Changing from a start/middle anchor to an end/middle anchor lets the label
    occupy the clear side of the same symbol without changing its text size.
    Candidate baselines remain inside the strict owner radius and are ordered by
    minimum displacement from the symbol center, then by movement from the
    initially projected location for deterministic, stable layouts.
    """
    symbol_bounds = _rotated_bounds(
        symbol.center, symbol.width, symbol.height, symbol.orientation_deg,
    )
    label_height = _label_scene_height(label.size_pt)
    clearance = 10.0
    step = _EQUIPMENT_LABEL_SEARCH_STEP

    # Each base placement puts the text envelope just outside the symbol.
    # The normal adjustment allows a candidate to move slightly inward or
    # outward when another object (for example, a neighboring bus) blocks the
    # exact edge-aligned position. Collision checks still protect the symbol.
    side_bases = (
        ("top", Point(symbol.center.x, symbol_bounds.y - clearance), "middle",
         (1.0, 0.0), (0.0, -1.0)),
        ("bottom", Point(
            symbol.center.x,
            symbol_bounds.bottom + clearance + label_height,
        ), "middle", (1.0, 0.0), (0.0, 1.0)),
        ("left", Point(
            symbol_bounds.x - clearance,
            symbol.center.y + label_height / 2.0,
        ), "end", (0.0, 1.0), (-1.0, 0.0)),
        ("right", Point(
            symbol_bounds.right + clearance,
            symbol.center.y + label_height / 2.0,
        ), "start", (0.0, 1.0), (1.0, 0.0)),
    )
    if label.anchor == "start":
        preferred_side = "right"
    elif label.anchor == "end":
        preferred_side = "left"
    else:
        preferred_side = "bottom" if label.position.y >= symbol.center.y else "top"

    candidates: list[tuple[Point, str, str, int]] = [
        (label.position, label.anchor, preferred_side, -1),
    ]
    tangent_steps = int(_EQUIPMENT_LABEL_MAX_TANGENT_SHIFT // step)
    normal_values = range(
        int(_EQUIPMENT_LABEL_MIN_NORMAL_ADJUSTMENT // step),
        int(_EQUIPMENT_LABEL_MAX_NORMAL_ADJUSTMENT // step) + 1,
    )
    for side_index, (side, base, anchor, tangent_axis, normal_axis) in enumerate(side_bases):
        for tangent_index in range(-tangent_steps, tangent_steps + 1):
            tangent = tangent_index * step
            for normal_index in normal_values:
                normal = normal_index * step
                position = Point(
                    base.x + tangent_axis[0] * tangent + normal_axis[0] * normal,
                    base.y + tangent_axis[1] * tangent + normal_axis[1] * normal,
                )
                distance = hypot(
                    position.x - symbol.center.x,
                    position.y - symbol.center.y,
                )
                if distance < _EQUIPMENT_LABEL_OWNER_RADIUS:
                    candidates.append((position, anchor, side, side_index))

    # Deduplicate identical baseline/anchor combinations before sorting.
    unique: dict[tuple[float, float, str], tuple[Point, str, str, int]] = {}
    for position, anchor, side, side_index in candidates:
        key = (round(position.x, 6), round(position.y, 6), anchor)
        current = unique.get(key)
        if current is None or side_index < current[3]:
            unique[key] = (position, anchor, side, side_index)

    ordered = sorted(
        unique.values(),
        key=lambda candidate: (
            0 if candidate[2] == preferred_side else 1,
            hypot(
                candidate[0].x - symbol.center.x,
                candidate[0].y - symbol.center.y,
            ),
            hypot(
                candidate[0].x - label.position.x,
                candidate[0].y - label.position.y,
            ),
            candidate[3],
            candidate[1],
            candidate[0].x,
            candidate[0].y,
        ),
    )
    return tuple((position, anchor) for position, anchor, _side, _side_index in ordered)


def _wire_bounds(first: Point, second: Point, clearance: float = 6.0) -> Rect:
    left = min(first.x, second.x) - clearance / 2.0
    top = min(first.y, second.y) - clearance / 2.0
    return Rect(left, top, max(clearance, abs(second.x - first.x) + clearance),
                max(clearance, abs(second.y - first.y) + clearance))


def project_network_to_diagram(workspace: NetworkWorkspace) -> DiagramDocument:
    """Create a compact 2D schematic from the canonical Network model."""
    if not isinstance(workspace, NetworkWorkspace):
        raise TypeError("workspace must be a NetworkWorkspace")
    network = workspace.network
    connection_by_terminal = _connected_bus_ids(network)
    bus_by_id = {item.id: item for item in network.buses}
    auto_positions, auto_orientations, auto_lengths = _automatic_bus_layout(
        network, workspace.grid_spacing
    )
    positions = dict(auto_positions)
    for identifier, pair in workspace.diagram_positions.items():
        if identifier in bus_by_id:
            positions[identifier] = Point(float(pair[0]), float(pair[1]))

    buses: list[EngineeringBus] = []
    bus_by_identifier: dict[UUID, EngineeringBus] = {}
    for bus in network.buses:
        center = positions[bus.id]
        inferred_orientation = auto_orientations.get(bus.id, 0.0)
        if bus.id in workspace.diagram_rotations:
            orientation = workspace.diagram_rotations[bus.id]
        elif bus.id in auto_orientations and len(network.buses) > 1:
            orientation = inferred_orientation
            # User-positioned substations are composed as horizontal busbar
            # systems. Feeder/end bars remain horizontal too; turning a busbar
            # vertical merely because it has one graph neighbour confuses a
            # feeder terminal with a separate busbar orientation convention.
            if bus.id in workspace.diagram_positions:
                orientation = 0.0
        else:
            orientation = 0.0
        length = auto_lengths.get(bus.id, _busbar_length(sum(1 for connection in network.connections if connection.bus_id == bus.id)))
        bus_kind = getattr(bus.kind, "value", str(bus.kind))
        bounds = (
            Rect(center.x - 6.0, center.y - 6.0, 12.0, 12.0)
            if bus_kind == "connection_node"
            else _bus_bounds(center, orientation, length)
        )
        projected = EngineeringBus(
            bus.id, bus.name, bus.nominal_voltage.value_kv, bounds, center,
            orientation, kind=bus_kind,
        )
        buses.append(projected)
        bus_by_identifier[bus.id] = projected

    placements_by_equipment = {
        item.equipment_id: item for item in workspace.diagram_symbols.values()
        if item.equipment_id is not None
    }
    automatic_equipment_layout = _automatic_equipment_layout(network, bus_by_identifier)
    preferred_equipment_positions = {
        identifier: value[0] for identifier, value in automatic_equipment_layout.items()
    }
    for equipment_id in {item.id for item in network.equipment}:
        if equipment_id in workspace.diagram_positions:
            x, y = workspace.diagram_positions[equipment_id]
            preferred_equipment_positions[equipment_id] = Point(float(x), float(y))
        placement = placements_by_equipment.get(equipment_id)
        if placement is not None:
            preferred_equipment_positions[equipment_id] = Point(float(placement.x), float(placement.y))
    terminal_bus_taps = _terminal_bus_taps(
        network, bus_by_identifier, preferred_equipment_positions
    )
    manually_positioned_equipment = set(workspace.diagram_positions) | set(placements_by_equipment)
    for equipment in network.equipment:
        terminals = tuple(equipment.terminals)
        if len(terminals) != 2 or equipment.id in manually_positioned_equipment:
            continue
        first_tap = terminal_bus_taps[terminals[0].id]
        second_tap = terminal_bus_taps[terminals[1].id]
        center, orientation = automatic_equipment_layout.get(equipment.id, (None, 0.0))
        if center is None:
            continue
        if abs(first_tap.x - second_tap.x) < 1e-6 and abs(abs(orientation) - 90.0) < 1e-6:
            automatic_equipment_layout[equipment.id] = (Point(first_tap.x, center.y), orientation)
        elif abs(first_tap.y - second_tap.y) < 1e-6 and abs(orientation % 180.0) < 1e-6:
            automatic_equipment_layout[equipment.id] = (Point((first_tap.x + second_tap.x) / 2.0, first_tap.y), orientation)
    symbols: list[EngineeringSymbol] = []
    conductors: list[EngineeringConductor] = []
    labels: list[EngineeringLabel] = []
    diagnostics: list[str] = []

    for bus in buses:
        if bus.kind == "connection_node":
            name_position = Point(bus.center.x, bus.center.y - 18.0)
            voltage_position = Point(bus.center.x, bus.center.y + 48.0)
            name_anchor = voltage_anchor = "middle"
        elif abs(bus.orientation_deg % 180.0) < 1e-6:
            name_position = Point(bus.center.x, bus.center.y - 20.0)
            voltage_position = Point(bus.center.x, bus.center.y + 48.0)
            name_anchor = voltage_anchor = "middle"
        else:
            label_x = bus.center.x - bus.bounds.width / 2.0 - 14.0
            name_position = Point(label_x, bus.center.y - 7.0)
            voltage_position = Point(label_x, bus.center.y + 20.0)
            name_anchor = voltage_anchor = "end"
        labels.append(_label(bus.bus_id, bus.name, name_position, anchor=name_anchor,
                             size_pt=9.2, weight="semibold", priority=10,
                             label_key="bus-name"))
        labels.append(_label(bus.bus_id, f"{bus.nominal_voltage_kv:g} kV", voltage_position,
                             anchor=voltage_anchor, size_pt=8.2, color="#526273", priority=40,
                             label_key="bus-voltage"))

    for equipment in network.equipment:
        family, state = _equipment_family(equipment)
        definition = get_symbol_definition(family)
        terminals = tuple(equipment.terminals)
        missing = [terminal for terminal in terminals if terminal.id not in connection_by_terminal]
        if missing:
            names = ", ".join(item.designation for item in missing)
            raise DiagramProjectionError(
                f"Equipment {equipment.name!r} has unconnected terminal(s): {names}. "
                "Connect every required terminal before generating the diagram."
            )
        connected_buses = [connection_by_terminal[item.id] for item in terminals]
        if any(bus_id not in bus_by_identifier for bus_id in connected_buses):
            raise DiagramProjectionError(f"Equipment {equipment.name!r} references an unknown bus.")
        width, height = definition.width, definition.height
        orientation = 0.0
        if len(terminals) == 1:
            bus = bus_by_identifier[connected_buses[0]]
            tap = terminal_bus_taps[terminals[0].id]
            center = _equipment_center_for_single_terminal(
                family, bus, tap, clearance=130.0
            )
            direction = -1.0 if family == "source" else 1.0
            if abs(bus.orientation_deg % 180.0) < 1e-6:
                terminal_local = (
                    (0.0, height / 2.0) if direction < 0 else (0.0, -height / 2.0)
                )
            else:
                terminal_local = (
                    (width / 2.0, 0.0) if direction < 0 else (-width / 2.0, 0.0)
                )
            terminal_points = (_transform_local(center, terminal_local, orientation),)
        elif len(terminals) == 2:
            first, second = (bus_by_identifier[item] for item in connected_buses)
            default_center, default_orientation = automatic_equipment_layout.get(
                equipment.id, (Point((first.center.x + second.center.x) / 2.0,
                                     (first.center.y + second.center.y) / 2.0), 90.0)
            )
            center = default_center
            orientation = default_orientation
            terminal_points = tuple(
                _transform_local(center, (item.x, item.y), orientation)
                for item in definition.terminals
            )
        else:
            raise DiagramProjectionError(
                f"Equipment {equipment.name!r} has {len(terminals)} terminals; "
                "the current symbol projection requires an explicitly documented symbol mapping."
            )

        placement = placements_by_equipment.get(equipment.id)
        if placement is not None:
            center = Point(placement.x, placement.y)
            orientation = placement.rotation_deg
            if len(terminals) == 1:
                terminal_points = (_transform_local(center, terminal_local, orientation),)
            elif len(definition.terminals) == len(terminals):
                terminal_points = tuple(
                    _transform_local(center, (item.x, item.y), orientation)
                    for item in definition.terminals
                )
        elif equipment.id in workspace.diagram_positions:
            x, y = workspace.diagram_positions[equipment.id]
            center = Point(x, y)
            if len(terminals) == 1:
                terminal_points = (_transform_local(center, terminal_local, orientation),)
            elif len(definition.terminals) == len(terminals):
                terminal_points = tuple(
                    _transform_local(center, (item.x, item.y), orientation)
                    for item in definition.terminals
                )

        symbols.append(EngineeringSymbol(
            equipment.id, equipment.name, family, center, width, height,
            tuple(item.id for item in terminals), terminal_points, state,
            orientation, "equipment", definition.symbol_id,
            tuple(item.designation for item in terminals),
        ))

        # Each terminal-to-bus wire terminates at a computed finite-busbar tap.
        for terminal, bus_id, terminal_point in zip(terminals, connected_buses, terminal_points, strict=True):
            bus = bus_by_identifier[bus_id]
            bus_point = terminal_bus_taps[terminal.id]
            conductors.append(EngineeringConductor(
                terminal.id, bus_id, _route_to_terminal(bus_point, terminal_point, bus)
            ))

        label_text = placement.label if placement is not None and placement.label else equipment.name
        label_side = (
            "below" if len(terminals) == 1
            and family in {"generator", "load", "capacitor", "reactor", "compensation"}
            else "above"
        )
        labels.extend(_layout_equipment_label(
            equipment.id, label_text, state, center, width, height, orientation,
            side=label_side,
        ))

    # State is encoded once in the drawing key, not repeated as long warning
    # strings beside every device. This preserves traceability without clutter.
    unresolved_count = sum(1 for item in symbols if item.state == "unresolved")
    partial_count = sum(1 for item in symbols if item.state == "partial-data")
    if unresolved_count or partial_count:
        lowest_y = max(
            [bus.bounds.bottom for bus in buses]
            + [symbol.center.y + symbol.height / 2.0 for symbol in symbols]
            + [label.position.y for label in labels]
        )
        left_x = min(bus.bounds.x for bus in buses)
        legend_y = lowest_y + 42.0
        if unresolved_count:
            labels.append(_label(
                None, "† Equipment parameters unresolved", Point(left_x, legend_y),
                anchor="start", size_pt=7.2, color="#8A5A12", priority=90,
                label_key=f"document-note:{network.id}:unresolved",
            ))
            legend_y += 20.0
        if partial_count:
            labels.append(_label(
                None, "‡ Sequence-network data incomplete", Point(left_x, legend_y),
                anchor="start", size_pt=7.2, color="#8A5A12", priority=91,
                label_key=f"document-note:{network.id}:sequence",
            ))

    # Persisted annotations override the generated field with the same owner/text role.
    if workspace.diagram_labels:
        overrides_by_id = {item.label_id: item for item in workspace.diagram_labels.values()}
        labels = [
            _user_label(overrides_by_id[item.label_id])
            if item.label_id in overrides_by_id else item
            for item in labels
        ]
        generated_ids = {item.label_id for item in labels}
        labels.extend(
            _user_label(item) for item in workspace.diagram_labels.values()
            if item.label_id not in generated_ids
        )

    # Global label pass: enforce a reserved halo around busbars and symbol envelopes.
    placed: list[Rect] = []
    normalized_labels: list[EngineeringLabel] = []
    equipment_symbol_by_id = {item.equipment_id: item for item in symbols}
    bus_by_id = {item.bus_id: item for item in buses}
    wire_obstacles = [
        _wire_bounds(first, second)
        for conductor in conductors
        for first, second in pairwise(conductor.points)
    ]
    wire_obstacles.extend(
        _wire_bounds(symbol.terminal_points[0], symbol.terminal_points[1])
        for symbol in symbols
        if symbol.family == "line" and len(symbol.terminal_points) == 2
    )
    for item in sorted(labels, key=lambda label: (label.priority, str(label.owner_id), label.text)):
        if not item.visible:
            normalized_labels.append(item)
            continue
        rect = _label_bounds(item)
        obstacles: list[Rect] = list(placed) + wire_obstacles
        if item.owner_id in equipment_symbol_by_id:
            symbol = equipment_symbol_by_id[item.owner_id]
            obstacles.append(_rotated_bounds(symbol.center, symbol.width, symbol.height,
                                             symbol.orientation_deg))
            obstacles.extend(bus.bounds for bus in buses)
            obstacles.extend(
                _rotated_bounds(other.center, other.width, other.height, other.orientation_deg)
                for other in symbols if other.equipment_id != item.owner_id
            )
        elif item.owner_id in bus_by_id:
            obstacles.extend(bus.bounds for bus in buses if bus.bus_id != item.owner_id)
            obstacles.extend(_rotated_bounds(other.center, other.width, other.height,
                                             other.orientation_deg) for other in symbols)
        else:
            obstacles.extend(bus.bounds for bus in buses)
            obstacles.extend(_rotated_bounds(other.center, other.width, other.height,
                                             other.orientation_deg) for other in symbols)
        # Generated layouts already assign distinct lanes. Shift only colliding
        # annotations; do not mutate their owner or model data. Equipment names
        # use a fine local search so collision resolution cannot send them far
        # away from the symbol merely because a coarse vertical candidate passed
        # before a smaller horizontal/diagonal correction was examined.
        owner_symbol = equipment_symbol_by_id.get(item.owner_id)
        if owner_symbol is not None and item.priority == 20:
            candidate_placements = _local_equipment_label_candidates(item, owner_symbol)
        else:
            step_x = max(10.0, min(24.0, rect.width * 0.22))
            step_y = max(12.0, rect.height * 1.20)
            offsets = [(0.0, 0.0)]
            for level in range(1, 9):
                dx, dy = step_x * level, step_y * level
                offsets.extend((
                    (-dx, 0.0), (dx, 0.0),
                    (0.0, -dy), (0.0, dy),
                    (-dx, -dy), (dx, -dy), (-dx, dy), (dx, dy),
                ))
            candidate_placements = tuple(
                (Point(item.position.x + dx, item.position.y + dy), item.anchor)
                for dx, dy in offsets
            )
        chosen = None
        chosen_anchor = item.anchor
        for candidate, candidate_anchor in candidate_placements:
            candidate_rect = _label_bounds_at(item, candidate, candidate_anchor)
            if not any(candidate_rect.intersects(block, clearance=3.0) for block in obstacles):
                chosen = candidate
                chosen_anchor = candidate_anchor
                rect = candidate_rect
                break
        if chosen is None:
            chosen = item.position
            chosen_anchor = item.anchor
            diagnostics.append(f"LABEL_COLLISION:{item.owner_id}:{item.text}")
        placed.append(rect)
        normalized_labels.append(EngineeringLabel(
            item.owner_id, item.text, chosen, chosen_anchor, item.label_id,
            item.font_family, item.size_pt, item.weight, item.color,
            item.rotation_deg, item.visible, item.layer, item.priority,
            item.unit, item.number_format,
        ))

    canonical_bus_ids = set(bus_by_id)
    if canonical_bus_ids != {item.bus_id for item in buses}:
        raise DiagramProjectionError("Not every canonical bus was projected.")
    projected_equipment = {item.equipment_id for item in symbols}
    canonical_equipment = {item.id for item in network.equipment}
    if projected_equipment != canonical_equipment:
        raise DiagramProjectionError("Equipment-to-symbol correspondence is not bijective.")
    canonical_connections = {(item.terminal_id, item.bus_id) for item in network.connections}
    projected_connections = {(item.terminal_id, item.bus_id) for item in conductors}
    if canonical_connections != projected_connections:
        raise DiagramProjectionError("Terminal-to-conductor correspondence is not bijective.")
    return DiagramDocument(network.id, network.name, tuple(buses), tuple(symbols),
                           tuple(conductors), tuple(normalized_labels), tuple(diagnostics))


def _rotated_bounds(center: Point, width: float, height: float, angle_deg: float) -> Rect:
    angle = radians(angle_deg % 180.0)
    rotated_width = abs(width * cos(angle)) + abs(height * sin(angle))
    rotated_height = abs(width * sin(angle)) + abs(height * cos(angle))
    return Rect(center.x - rotated_width / 2.0, center.y - rotated_height / 2.0,
                max(rotated_width, 0.1), max(rotated_height, 0.1))


def validate_diagram_document(
    workspace: NetworkWorkspace, document: DiagramDocument
) -> tuple[str, ...]:
    """Validate that a diagram is a lossless projection of its canonical network.

    Identity/cardinality checks deliberately use ordered records and counters, not
    only frozensets: sets conceal duplicate symbols, terminals and conductors.
    The drawing remains presentation-only; this validator never infers an
    electrical junction from a graphical crossing.
    """
    errors: list[str] = []
    tolerance = 1e-6
    network = workspace.network

    if document.network_id != network.id:
        errors.append("network identity mismatch")

    expected_bus_ids = {item.id for item in network.buses}
    projected_bus_ids = [item.bus_id for item in document.buses]
    projected_bus_id_set = set(projected_bus_ids)
    if len(projected_bus_ids) != len(projected_bus_id_set):
        errors.append("duplicate bus projection identity")
    if projected_bus_id_set != expected_bus_ids or len(projected_bus_ids) != len(expected_bus_ids):
        errors.append("bus projection mismatch")
    bus_by_id = {item.bus_id: item for item in document.buses}

    equipment_by_id = {item.id: item for item in network.equipment}
    expected_equipment_ids = set(equipment_by_id)
    projected_equipment_ids = [item.equipment_id for item in document.symbols]
    projected_equipment_id_set = set(projected_equipment_ids)
    if len(projected_equipment_ids) != len(projected_equipment_id_set):
        errors.append("duplicate equipment symbol projection")
    if (
        projected_equipment_id_set != expected_equipment_ids
        or len(projected_equipment_ids) != len(expected_equipment_ids)
    ):
        errors.append("equipment/symbol mismatch")
    symbol_by_id = {item.equipment_id: item for item in document.symbols}

    terminal_owner: dict[UUID, UUID] = {}
    expected_terminal_ids: set[UUID] = set()
    for equipment in network.equipment:
        for terminal in equipment.terminals:
            expected_terminal_ids.add(terminal.id)
            terminal_owner[terminal.id] = equipment.id

    projected_terminal_ids = [
        terminal_id for symbol in document.symbols for terminal_id in symbol.terminal_ids
    ]
    projected_terminal_id_set = set(projected_terminal_ids)
    if len(projected_terminal_ids) != len(projected_terminal_id_set):
        errors.append("duplicate terminal in symbol projection")
    if (
        projected_terminal_id_set != expected_terminal_ids
        or len(projected_terminal_ids) != len(expected_terminal_ids)
    ):
        errors.append("terminal/symbol mismatch")

    symbol_terminal_points: dict[UUID, Point] = {}
    for symbol in document.symbols:
        if symbol.width <= 0 or symbol.height <= 0:
            errors.append(f"invalid symbol dimensions: {symbol.name}")
        if len(symbol.terminal_ids) != len(symbol.terminal_points):
            errors.append(f"symbol terminal cardinality mismatch: {symbol.name}")
        if not symbol.symbol_id:
            errors.append(f"symbol definition missing: {symbol.name}")
        equipment = equipment_by_id.get(symbol.equipment_id)
        if equipment is None:
            errors.append(f"symbol references unknown equipment: {symbol.equipment_id}")
            continue
        expected_for_equipment = tuple(item.id for item in equipment.terminals)
        if symbol.terminal_ids != expected_for_equipment:
            errors.append(f"symbol terminal ownership mismatch: {symbol.name}")
        for terminal_id, terminal_point in zip(symbol.terminal_ids, symbol.terminal_points):
            if terminal_owner.get(terminal_id) != symbol.equipment_id:
                errors.append(f"symbol terminal ownership mismatch: {symbol.name}")
            if terminal_id in symbol_terminal_points:
                errors.append(f"terminal has multiple symbol pins: {terminal_id}")
            else:
                symbol_terminal_points[terminal_id] = terminal_point

    for bus in document.buses:
        if bus.bounds.width <= 0 or bus.bounds.height <= 0:
            errors.append(f"invalid busbar dimensions: {bus.name}")

    expected_connection_by_terminal = {
        item.terminal_id: item.bus_id for item in network.connections
    }
    expected_connection_pairs = set(expected_connection_by_terminal.items())
    if len(expected_connection_by_terminal) != len(network.connections):
        errors.append("canonical network contains duplicate terminal connections")
    if set(expected_connection_by_terminal) != expected_terminal_ids:
        errors.append("canonical network has missing or unknown terminal connections")

    conductor_terminal_ids = [item.terminal_id for item in document.conductors]
    conductor_terminal_id_set = set(conductor_terminal_ids)
    if len(conductor_terminal_ids) != len(conductor_terminal_id_set):
        errors.append("duplicate conductor terminal projection")
    if (
        conductor_terminal_id_set != set(expected_connection_by_terminal)
        or len(conductor_terminal_ids) != len(expected_connection_by_terminal)
    ):
        errors.append("conductor/connection cardinality mismatch")
    actual_connection_pairs = {(item.terminal_id, item.bus_id) for item in document.conductors}
    if (
        actual_connection_pairs != expected_connection_pairs
        or len(document.conductors) != len(expected_connection_pairs)
    ):
        errors.append("terminal/connection mismatch")

    for conductor in document.conductors:
        if conductor.terminal_id not in expected_connection_by_terminal:
            errors.append(f"conductor references unknown terminal: {conductor.terminal_id}")
        elif expected_connection_by_terminal[conductor.terminal_id] != conductor.bus_id:
            errors.append(f"conductor connected to wrong bus: {conductor.terminal_id}")

        if len(conductor.points) < 2:
            errors.append(f"conductor has fewer than two points: {conductor.terminal_id}")
            continue
        if any(first == second for first, second in pairwise(conductor.points)):
            errors.append(f"conductor contains zero-length segment: {conductor.terminal_id}")
        for first, second in pairwise(conductor.points):
            if abs(first.x - second.x) > tolerance and abs(first.y - second.y) > tolerance:
                errors.append(
                    f"non-orthogonal conductor segment at terminal {conductor.terminal_id}"
                )
        direct_manhattan = (
            abs(conductor.points[-1].x - conductor.points[0].x)
            + abs(conductor.points[-1].y - conductor.points[0].y)
        )
        actual_manhattan = sum(
            abs(second.x - first.x) + abs(second.y - first.y)
            for first, second in pairwise(conductor.points)
        )
        if actual_manhattan > direct_manhattan + tolerance:
            errors.append(f"non-minimal orthogonal route at terminal {conductor.terminal_id}")

        bus = bus_by_id.get(conductor.bus_id)
        if bus is None:
            errors.append(f"conductor references unknown bus: {conductor.bus_id}")
        else:
            start_point = conductor.points[0]
            horizontal = abs(bus.orientation_deg % 180.0) < tolerance
            if horizontal:
                on_bus_axis = abs(start_point.y - bus.center.y) <= tolerance
                within_extent = (
                    bus.bounds.x - tolerance <= start_point.x <= bus.bounds.right + tolerance
                )
                perpendicular = abs(conductor.points[1].x - start_point.x) <= tolerance
            else:
                on_bus_axis = abs(start_point.x - bus.center.x) <= tolerance
                within_extent = (
                    bus.bounds.y - tolerance <= start_point.y <= bus.bounds.bottom + tolerance
                )
                perpendicular = abs(conductor.points[1].y - start_point.y) <= tolerance
            if not on_bus_axis or not within_extent:
                errors.append(f"conductor tap is outside its busbar: {conductor.terminal_id}")
            if not perpendicular:
                errors.append(
                    f"bus departure is not perpendicular at terminal {conductor.terminal_id}"
                )

        expected_terminal_point = symbol_terminal_points.get(conductor.terminal_id)
        if expected_terminal_point is not None and conductor.points[-1] != expected_terminal_point:
            owner_id = terminal_owner.get(conductor.terminal_id)
            owner_symbol = symbol_by_id.get(owner_id)
            owner_name = owner_symbol.name if owner_symbol is not None else str(owner_id)
            errors.append(f"conductor terminal mismatch for equipment {owner_name}")

    visible_labels = [item for item in document.labels if item.visible]
    wire_bounds = [
        _wire_bounds(first, second)
        for conductor in document.conductors
        for first, second in pairwise(conductor.points)
    ]
    wire_bounds.extend(
        _wire_bounds(symbol.terminal_points[0], symbol.terminal_points[1])
        for symbol in document.symbols
        if symbol.family == "line" and len(symbol.terminal_points) == 2
    )
    for index, label in enumerate(visible_labels):
        bounds = _label_bounds(label)
        for wire in wire_bounds:
            if bounds.intersects(wire):
                errors.append(f"label overlaps conductor: {label.text!r}")
        for symbol in document.symbols:
            symbol_bounds = _rotated_bounds(
                symbol.center, symbol.width, symbol.height, symbol.orientation_deg
            )
            if symbol.equipment_id != label.owner_id and bounds.intersects(symbol_bounds):
                errors.append(f"label overlaps equipment symbol {symbol.name}")
        for other in visible_labels[index + 1:]:
            if bounds.intersects(_label_bounds(other), clearance=2.0):
                errors.append(f"label collision: {label.text!r} / {other.text!r}")
    return tuple(dict.fromkeys(errors))

