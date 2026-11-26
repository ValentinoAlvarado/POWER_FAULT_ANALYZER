"""Canonical electrical-model projection and compact engineering composition.

The physical Network aggregate remains authoritative for equipment, terminals and
connections.  This module computes only presentation geometry and independent
annotation placements; it never changes the electrical model or infers topology
from intersections in the drawing.
"""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from math import atan2, cos, degrees, hypot, radians, sin
from uuid import UUID, NAMESPACE_URL, uuid5

from power_fault_analyzer.application.use_cases.network_workspace import (
    DiagramLabelPlacement,
    NetworkWorkspace,
)
from power_fault_analyzer.domain.aggregates.network import Network
from power_fault_analyzer.equipment.interfaces.unresolved_branch import UnresolvedTwoTerminalEquipment
from power_fault_analyzer.equipment.interfaces.unresolved_equipment import UnresolvedEquipmentInterface
from power_fault_analyzer.equipment.interfaces.unresolved_single_terminal import UnresolvedSingleTerminalEquipment
from power_fault_analyzer.equipment.sources.equivalent_source import EquivalentSource
from power_fault_analyzer.equipment.sources.synchronous_generator import SynchronousGenerator
from power_fault_analyzer.equipment.switching.switching_device import SwitchingDevice
from power_fault_analyzer.equipment.transmission.line import Line
from power_fault_analyzer.equipment.transformers.two_winding_transformer import TwoWindingTransformer

from .layout import Point, Rect, perpendicular_bay_route, snap_point
from .symbol_catalog import SYMBOL_CATALOG, get_symbol_definition


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
    font_family: str = "STIX Two Text"
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
_LABEL_SCENE_UNITS_PER_PT = 2.8


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
        if equipment.equipment_kind == "source":
            from power_fault_analyzer.domain.enums.equipment_interface import ParameterEvidenceStatus
            confirmed = any(
                item.status is ParameterEvidenceStatus.USER_CONFIRMED
                for item in equipment.parameters
            )
            unresolved = any(item.status in {
                ParameterEvidenceStatus.UNRESOLVED,
                ParameterEvidenceStatus.CONFLICTING,
            } for item in equipment.parameters)
            return "source", "partial-data" if confirmed and unresolved else "unresolved"
        if equipment.equipment_kind in {"generator", "synchronous_generator"}:
            return "generator", "unresolved"
        return "generic", "unresolved"
    if isinstance(equipment, (UnresolvedTwoTerminalEquipment, UnresolvedEquipmentInterface)):
        kind = equipment.equipment_kind if isinstance(equipment, UnresolvedTwoTerminalEquipment) else (
            "line" if equipment.interface_kind.value == "transmission_line" else "transformer"
        )
        if kind in {"line", "transmission_line"}:
            return "line", "unresolved"
        if kind in {"transformer", "two_winding_transformer"}:
            return "transformer", "unresolved"
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


def _busbar_length(terminal_count: int) -> float:
    """Size a finite busbar from its explicit connected-terminal incidence.

    Graph degree alone is insufficient: a source shunt and a line terminal both
    occupy real bays on the same bus even when the bus has only one neighbour.
    The minimum length prevents one-bay buses from collapsing into short stubs;
    each additional canonical terminal receives a fixed bay allowance.
    """
    if terminal_count < 0:
        raise ValueError("terminal_count cannot be negative")
    return min(
        _BUS_MAX_LENGTH,
        _BUS_MIN_LENGTH + max(0, terminal_count - 1) * _BUS_LENGTH_PER_EXTRA_TERMINAL,
    )


def _automatic_bus_layout(network: Network, grid: float):
    """Place every busbar on its own row so bays enter/leave it perpendicularly.

    A previous two-row serpentine placed adjacent buses at the same Y coordinate.
    The equipment between those buses was consequently drawn inline with the
    busbars, visually turning distinct electrical nodes into one continuous bar.
    The current layout gives every bus a unique row and lets two-terminal bay
    equipment run vertically between rows.  X alternates to keep path networks
    compact without making a branch collinear with a busbar.
    """
    adjacency, _equipment_by_pair, shunts = _topology(network)
    terminal_counts: dict[UUID, int] = {bus.id: 0 for bus in network.buses}
    for connection in network.connections:
        terminal_counts[connection.bus_id] = terminal_counts.get(connection.bus_id, 0) + 1

    positions: dict[UUID, Point] = {}
    orientations: dict[UUID, float] = {}
    lengths: dict[UUID, float] = {}
    ordered_path = _path_order(network, adjacency, shunts)
    # Keep adjacent automatic bus rows close enough to share a wide physical
    # bay corridor.  This is what permits terminal taps on connected bars to
    # align on one vertical lane instead of forcing long lateral dog-legs.
    x_left, x_right = 360.0, 420.0
    y_top, row_spacing = 220.0, 180.0

    if ordered_path is not None:
        for index, bus_id in enumerate(ordered_path):
            x = x_left if index % 2 == 0 else x_right
            y = y_top + index * row_spacing
            positions[bus_id] = snap_point(Point(x, y), grid)
            orientations[bus_id] = 0.0
            lengths[bus_id] = _busbar_length(terminal_counts.get(bus_id, 0))
        return positions, orientations, lengths

    # Branching/cyclic networks: breadth-first discovery assigns a unique row
    # to every bus.  Depth alternates between two compact columns; connected
    # equipment is still rendered vertically and its conductors dog-leg only
    # after leaving each horizontal busbar.
    bus_order = {bus.id: index for index, bus in enumerate(network.buses)}
    source_priority = _source_priority(network, shunts)
    roots = sorted(
        network.buses,
        key=lambda bus: (source_priority.get(bus.id, 9), bus_order[bus.id]),
    )
    depth: dict[UUID, int] = {}
    component_by_bus: dict[UUID, int] = {}
    discovered: list[UUID] = []
    component = 0
    for root in roots:
        if root.id in depth:
            continue
        queue = deque([root.id])
        depth[root.id] = 0
        component_by_bus[root.id] = component
        while queue:
            current = queue.popleft()
            discovered.append(current)
            for neighbor in sorted(adjacency[current], key=lambda item: bus_order[item]):
                if neighbor not in depth:
                    depth[neighbor] = depth[current] + 1
                    component_by_bus[neighbor] = component
                    queue.append(neighbor)
        component += 1

    row_by_bus = {bus_id: row for row, bus_id in enumerate(discovered)}
    component_x = {index: index * 440.0 for index in range(component)}
    for bus_id in discovered:
        component_index = component_by_bus[bus_id]
        column = depth[bus_id] % 2
        x = x_left + column * (x_right - x_left) + component_x[component_index]
        y = y_top + row_by_bus[bus_id] * row_spacing
        positions[bus_id] = snap_point(Point(x, y), grid)
        orientations[bus_id] = 0.0
        lengths[bus_id] = _busbar_length(terminal_counts.get(bus_id, 0))
    return positions, orientations, lengths


def _bus_bounds(center: Point, orientation: float, length: float) -> Rect:
    if abs(orientation % 180.0) < 1e-6:
        return Rect(center.x - length / 2.0, center.y - _BUS_THICKNESS / 2.0,
                    length, _BUS_THICKNESS)
    return Rect(center.x - _BUS_THICKNESS / 2.0, center.y - length / 2.0,
                _BUS_THICKNESS, length)


def _bus_tap(bus: EngineeringBus, target: Point) -> Point:
    """Nearest explicit tap on the finite busbar segment."""
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
    return EngineeringLabel(owner_id, text, position, anchor, label_id, "STIX Two Text",
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
    extent = max(width, height) / 2.0
    if side == "below":
        label_anchor = Point(center.x, center.y + extent + 18.0)
        anchor = "middle"
        warning_anchor = Point(center.x, label_anchor.y + 15.0)
    elif side == "right":
        label_anchor = Point(center.x + extent + 18.0, center.y + 3.0)
        anchor = "start"
        warning_anchor = Point(label_anchor.x, label_anchor.y + 15.0)
    elif side == "left":
        label_anchor = Point(center.x - extent - 18.0, center.y + 3.0)
        anchor = "end"
        warning_anchor = Point(label_anchor.x, label_anchor.y + 15.0)
    elif abs(orientation_deg % 180.0) > 1e-6:
        label_anchor = Point(center.x + extent + 18.0, center.y + 3.0)
        anchor = "start"
        warning_anchor = Point(label_anchor.x, label_anchor.y + 15.0)
    else:
        label_anchor = Point(center.x, center.y - extent - 15.0)
        anchor = "middle"
        warning_anchor = Point(center.x, label_anchor.y + 15.0)
    if state == "unresolved":
        name = f"{name}†"
    elif state == "partial-data":
        name = f"{name}‡"
    return (_label(equipment_id, name, label_anchor, anchor=anchor,
                   size_pt=7.4, weight="semibold", priority=20,
                   label_key="equipment-name"),)


def _equipment_center_for_single_terminal(
    family: str, bus: EngineeringBus, tap: Point,
) -> Point:
    """Place a one-terminal device directly above/below its reserved bus tap."""
    if abs(bus.orientation_deg % 180.0) < 1e-6:
        # A shunt bay occupies the adjacent vertical corridor.  Do not place it
        # beyond half the busbar length: doing so can overlap the next bus row.
        y = bus.center.y - 72.0 if family == "source" else bus.center.y + 72.0
        return Point(tap.x, y)
    x = (bus.center.x - length / 2.0 - 70.0 if family == "source"
         else bus.center.x + length / 2.0 + 70.0)
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
    if abs(bus.orientation_deg % 180.0) < 1e-6:
        return Point(coordinate, bus.center.y)
    return Point(bus.center.x, coordinate)


def _available_bus_axis(bus: EngineeringBus) -> tuple[float, float, float]:
    """Return the usable scalar interval and center of a finite busbar."""
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
) -> dict[UUID, Point]:
    """Allocate unique taps and align both ends of each bay on a shared lane.

    Two-terminal equipment receives one common X (or Y for vertical bars) at
    both connected buses whenever their finite extents overlap.  This makes
    default bay conductors straight and perpendicular instead of introducing
    needless horizontal jogs.  Shunt equipment is then placed over its own
    free tap.  All assignments come from canonical terminal-to-bus links.
    """
    equipment_by_terminal = {
        terminal.id: (equipment, terminal)
        for equipment in network.equipment
        for terminal in equipment.terminals
    }
    bus_by_terminal = {item.terminal_id: item.bus_id for item in network.connections}
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
                preferred = (low + high) / 2.0
                # The selected coordinate must be free on both buses. Search the
                # common interval by increasing distance from its center.
                steps = max(1, int((high - low) // 2.0))
                candidates = [low + (high - low) * index / steps for index in range(steps + 1)]
                candidates.sort(key=lambda value: (abs(value - preferred), value))
                # Keep separate bay equipment envelopes apart. The minimum
                # preferred lane separation is based on the widest built-in
                # symbols; only constrained/manual bar overlaps relax it.
                already_used = occupied[first_bus.bus_id] + occupied[second_bus.bus_id]
                chosen = next((value for value in candidates
                               if all(abs(value - used) >= 56.0 - 1e-7
                                      for used in already_used)), None)
                if chosen is None:
                    chosen = next((value for value in candidates
                                   if all(abs(value - used) >= 36.0 - 1e-7
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
            if family == "source":
                preferred = center - bus.length * 0.30
            elif family == "generator":
                preferred = center + bus.length * 0.30
            else:
                preferred = center
            coordinate = _choose_free_tap(
                bus, occupied[bus_id], preferred, minimum_separation=56.0
            )
            result[terminal.id] = _tap_point(bus, coordinate)
            occupied[bus_id].append(coordinate)
    return result


def _label_bounds(label: EngineeringLabel) -> Rect:
    # size_pt is a physical typographic size. Convert it to drawing-space
    # clearance using the default publication scale; the SVG renderer then
    # maps the exact point size to the chosen page dimensions.
    width = max(24.0, len(label.text) * label.size_pt * 0.54 * _LABEL_SCENE_UNITS_PER_PT)
    height = max(12.0, label.size_pt * 1.25 * _LABEL_SCENE_UNITS_PER_PT)
    if label.anchor == "middle":
        left = label.position.x - width / 2.0
    elif label.anchor == "end":
        left = label.position.x - width
    else:
        left = label.position.x
    return Rect(left, label.position.y - height, width, height)


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

    adjacency, equipment_by_pair, shunts = _topology(network)
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
        if bus.id in workspace.diagram_positions and bus.id not in workspace.diagram_rotations:
            length = _busbar_length(sum(
                1 for connection in network.connections if connection.bus_id == bus.id
            ))
        bounds = _bus_bounds(center, orientation, length)
        projected = EngineeringBus(bus.id, bus.name, bus.nominal_voltage.value_kv,
                                   bounds, center, orientation)
        buses.append(projected)
        bus_by_identifier[bus.id] = projected

    terminal_bus_taps = _terminal_bus_taps(network, bus_by_identifier)

    placements_by_equipment = {
        item.equipment_id: item for item in workspace.diagram_symbols.values()
        if item.equipment_id is not None
    }
    symbols: list[EngineeringSymbol] = []
    conductors: list[EngineeringConductor] = []
    labels: list[EngineeringLabel] = []
    diagnostics: list[str] = []

    for bus in buses:
        if abs(bus.orientation_deg % 180.0) < 1e-6:
            # Put both identifiers beyond the physical right end of the bar.
            # This keeps bay drops and junctions clear of bus names/voltages.
            label_x = bus.bounds.right + 12.0
            name_position = Point(label_x, bus.center.y - 8.0)
            voltage_position = Point(label_x, bus.center.y + 15.0)
            name_anchor = voltage_anchor = "start"
        else:
            label_x = bus.center.x - 16.0
            name_position = Point(label_x, bus.center.y - bus.bounds.height / 2.0 - 18.0)
            voltage_position = Point(label_x, bus.center.y + bus.bounds.height / 2.0 + 19.0)
            name_anchor = voltage_anchor = "end"
        labels.append(_label(bus.bus_id, bus.name, name_position, anchor=name_anchor,
                             size_pt=7.5, weight="semibold", priority=10,
                             label_key="bus-name"))
        labels.append(_label(bus.bus_id, f"{bus.nominal_voltage_kv:g} kV", voltage_position,
                             anchor=voltage_anchor, size_pt=6.8, color="#526273", priority=40,
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
            center = _equipment_center_for_single_terminal(family, bus, tap)
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
            # Bay equipment is vertical between horizontal busbars.  Its pins
            # are therefore perpendicular to both busbars by construction.
            first_tap = terminal_bus_taps[terminals[0].id]
            second_tap = terminal_bus_taps[terminals[1].id]
            if abs(second.center.y - first.center.y) < 1e-6:
                # Preserve manually aligned buses while moving the device into
                # a dedicated bay corridor below them; it must not split a bar.
                orientation = 90.0
                center = Point((first_tap.x + second_tap.x) / 2.0,
                               first.center.y + max(110.0, definition.width / 2.0 + 48.0))
            else:
                orientation = 90.0 if second.center.y > first.center.y else -90.0
                center = Point((first_tap.x + second_tap.x) / 2.0,
                               (first.center.y + second.center.y) / 2.0)
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
            terminal_points = tuple(
                _transform_local(center, (item.x, item.y), orientation)
                for item in definition.terminals
            )
        elif equipment.id in workspace.diagram_positions:
            x, y = workspace.diagram_positions[equipment.id]
            center = Point(x, y)
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
        label_side = "below" if family == "generator" and len(terminals) == 1 else "above"
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
        legend_y = lowest_y + 74.0
        if unresolved_count:
            labels.append(_label(
                None, "† Equipment parameters unresolved", Point(left_x, legend_y),
                anchor="start", size_pt=6.2, color="#8A5A12", priority=90,
                label_key=f"document-note:{network.id}:unresolved",
            ))
            legend_y += 17.0
        if partial_count:
            labels.append(_label(
                None, "‡ Sequence-network data incomplete", Point(left_x, legend_y),
                anchor="start", size_pt=6.2, color="#8A5A12", priority=91,
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
        for first, second in zip(conductor.points, conductor.points[1:])
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
        # annotations; do not mutate their owner or model data.
        step_x = max(10.0, min(24.0, rect.width * 0.22))
        step_y = max(12.0, rect.height * 1.20)
        candidate_offsets: list[tuple[float, float]] = [(0.0, 0.0)]
        # Prefer a short horizontal adjustment before moving text away from its
        # equipment. Expand the search radially only when the local halo is busy.
        for level in range(1, 9):
            dx, dy = step_x * level, step_y * level
            candidate_offsets.extend((
                (-dx, 0.0), (dx, 0.0),
                (0.0, -dy), (0.0, dy),
                (-dx, -dy), (dx, -dy), (-dx, dy), (dx, dy),
            ))
        chosen = None
        for offset_x, offset_y in candidate_offsets:
            candidate = Point(item.position.x + offset_x, item.position.y + offset_y)
            candidate_rect = Rect(rect.x + offset_x, rect.y + offset_y, rect.width, rect.height)
            if not any(candidate_rect.intersects(block, clearance=3.0) for block in obstacles):
                chosen = candidate
                rect = candidate_rect
                break
        if chosen is None:
            chosen = item.position
            diagnostics.append(f"LABEL_COLLISION:{item.owner_id}:{item.text}")
        placed.append(rect)
        normalized_labels.append(EngineeringLabel(
            item.owner_id, item.text, chosen, item.anchor, item.label_id,
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


def validate_diagram_document(workspace: NetworkWorkspace, document: DiagramDocument) -> tuple[str, ...]:
    """Check canonical identity, terminal correspondence and presentation geometry."""
    errors: list[str] = []
    network = workspace.network
    if document.network_id != network.id:
        errors.append("network identity mismatch")
    if document.equipment_ids != frozenset(item.id for item in network.equipment):
        errors.append("equipment/symbol mismatch")
    if document.terminal_ids != frozenset(
        terminal.id for equipment in network.equipment for terminal in equipment.terminals
    ):
        errors.append("terminal/symbol mismatch")
    expected = frozenset((item.terminal_id, item.bus_id) for item in network.connections)
    if document.connection_pairs != expected:
        errors.append("terminal/connection mismatch")
    symbol_by_id = {item.equipment_id: item for item in document.symbols}
    terminal_owner = {
        terminal.id: equipment.id
        for equipment in network.equipment for terminal in equipment.terminals
    }
    for symbol in document.symbols:
        if symbol.width <= 0 or symbol.height <= 0:
            errors.append(f"invalid symbol dimensions: {symbol.name}")
        if len(symbol.terminal_ids) != len(symbol.terminal_points):
            errors.append(f"symbol terminal cardinality mismatch: {symbol.name}")
        if not symbol.symbol_id:
            errors.append(f"symbol definition missing: {symbol.name}")
    for bus in document.buses:
        if bus.bounds.width <= 0 or bus.bounds.height <= 0:
            errors.append(f"invalid busbar dimensions: {bus.name}")
    bus_by_id = {item.bus_id: item for item in document.buses}
    for conductor in document.conductors:
        if not conductor.points:
            errors.append(f"empty conductor for terminal {conductor.terminal_id}")
            continue
        for first, second in zip(conductor.points, conductor.points[1:]):
            if first.x != second.x and first.y != second.y:
                errors.append(f"non-orthogonal conductor segment at terminal {conductor.terminal_id}")
        direct_manhattan = (abs(conductor.points[-1].x - conductor.points[0].x)
                            + abs(conductor.points[-1].y - conductor.points[0].y))
        actual_manhattan = sum(
            abs(second.x - first.x) + abs(second.y - first.y)
            for first, second in zip(conductor.points, conductor.points[1:])
        )
        if actual_manhattan > direct_manhattan + 1e-6:
            errors.append(f"non-minimal orthogonal route at terminal {conductor.terminal_id}")
        bus = bus_by_id.get(conductor.bus_id)
        if bus is not None and abs(bus.orientation_deg % 180.0) < 1e-6 and len(conductor.points) > 1:
            first_segment = conductor.points[1]
            if abs(first_segment.x - conductor.points[0].x) > 1e-6:
                errors.append(f"bus departure is not perpendicular at terminal {conductor.terminal_id}")
        owner = terminal_owner.get(conductor.terminal_id)
        if owner in symbol_by_id and conductor.points[-1] not in symbol_by_id[owner].terminal_points:
            errors.append(f"conductor terminal mismatch for equipment {symbol_by_id[owner].name}")
    visible_labels = [item for item in document.labels if item.visible]
    wire_bounds = [
        _wire_bounds(first, second)
        for conductor in document.conductors
        for first, second in zip(conductor.points, conductor.points[1:])
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
            symbol_bounds = _rotated_bounds(symbol.center, symbol.width, symbol.height,
                                            symbol.orientation_deg)
            if symbol.equipment_id != label.owner_id and bounds.intersects(symbol_bounds):
                errors.append(f"label overlaps equipment symbol {symbol.name}")
        for other in visible_labels[index + 1:]:
            if bounds.intersects(_label_bounds(other), clearance=2.0):
                errors.append(f"label collision: {label.text!r} / {other.text!r}")
    return tuple(dict.fromkeys(errors))
