"""Deterministic topology-aware diagram layout from explicit graph relationships."""
from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Iterable
from dataclasses import dataclass

from .layout import Point, Rect


@dataclass(frozen=True, slots=True)
class LayoutNode:
    identifier: str
    width: float = 48.0
    height: float = 48.0
    family: str = "equipment"


@dataclass(frozen=True, slots=True)
class LayoutEdge:
    source: str
    target: str
    identifier: str


@dataclass(frozen=True, slots=True)
class TopologyLayout:
    positions: dict[str, Point]
    bounds: dict[str, Rect]
    layers: tuple[tuple[str, ...], ...]


@dataclass(frozen=True, slots=True)
class BayLaneRequest:
    """Horizontal envelope for one equipment bay on a vertical topology span."""

    identifier: str
    start: float
    end: float
    preferred_x: float
    width: float

    def __post_init__(self) -> None:
        from math import isfinite

        if not self.identifier:
            raise ValueError("Bay lane identifiers must be non-empty.")
        if not all(isfinite(value) for value in (self.start, self.end, self.preferred_x, self.width)):
            raise ValueError("Bay lane geometry must be finite.")
        if self.end <= self.start or self.width <= 0.0:
            raise ValueError("Bay lane spans and widths must be positive.")


def layout_bay_lanes(
    requests: Iterable[BayLaneRequest], *, gap: float = 36.0,
    search_step: float = 80.0, max_rings: int = 256,
) -> dict[str, float]:
    """Allocate stable equipment columns without overlapping active bay spans.

    Each request owns a horizontal visual envelope over a vertical interval.
    Envelopes may reuse a column only when their vertical intervals do not
    overlap. Otherwise the allocator searches symmetric offsets from the
    topology-derived preferred column. Coordinates are presentation-only.
    """
    from math import isfinite

    if not isfinite(gap) or gap < 0.0 or not isfinite(search_step) or search_step <= 0.0:
        raise ValueError("Bay lane gap and search step must be finite and non-negative/positive.")
    if isinstance(max_rings, bool) or not isinstance(max_rings, int) or max_rings < 1:
        raise ValueError("max_rings must be a positive integer.")
    items = tuple(requests)
    identifiers = [item.identifier for item in items]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("Bay lane identifiers must be unique.")
    placed: list[tuple[BayLaneRequest, float]] = []
    result: dict[str, float] = {}
    for request in sorted(items, key=lambda item: (item.start, item.end, item.preferred_x, item.identifier)):
        step = max(search_step, request.width + gap)
        candidates = [request.preferred_x]
        for ring in range(1, max_rings + 1):
            candidates.extend((request.preferred_x + ring * step, request.preferred_x - ring * step))
        chosen = None
        for candidate in candidates:
            conflict = False
            for other, other_x in placed:
                vertical_overlap = not (request.end <= other.start or other.end <= request.start)
                horizontal_overlap = abs(candidate - other_x) < (request.width + other.width) / 2.0 + gap
                if vertical_overlap and horizontal_overlap:
                    conflict = True
                    break
            if not conflict:
                chosen = candidate
                break
        if chosen is None:
            raise ValueError(f"Could not allocate a collision-free lane for bay {request.identifier!r}.")
        placed.append((request, chosen))
        result[request.identifier] = chosen
    return result


def layout_topology(
    nodes: Iterable[LayoutNode], edges: Iterable[LayoutEdge], *,
    origin: Point | None = None, grid: float = 20.0,
    horizontal_gap: float = 120.0, vertical_gap: float = 100.0,
) -> TopologyLayout:
    """Layer a directed drawing graph; cycles are handled deterministically.

    Edges describe visual/logical relationships supplied by the caller. They are
    not electrical connections unless built from the canonical network model.
    """
    if origin is None:
        origin = Point(80.0, 80.0)
    node_list = tuple(nodes)
    ids = [node.identifier for node in node_list]
    if len(ids) != len(set(ids)):
        raise ValueError("Node identifiers must be unique.")
    by_id = {node.identifier: node for node in node_list}
    if any(n.width <= 0 or n.height <= 0 for n in node_list):
        raise ValueError("Node dimensions must be positive.")
    outgoing: dict[str, set[str]] = defaultdict(set)
    indegree = {identifier: 0 for identifier in ids}
    for edge in edges:
        if edge.source not in by_id or edge.target not in by_id:
            raise ValueError(f"Edge {edge.identifier!r} references an unknown node.")
        if edge.target not in outgoing[edge.source]:
            outgoing[edge.source].add(edge.target)
            indegree[edge.target] += 1
    queue = deque(sorted(identifier for identifier, degree in indegree.items() if degree == 0))
    depth = {identifier: 0 for identifier in queue}
    visited = set()
    while queue:
        current = queue.popleft()
        visited.add(current)
        for target in sorted(outgoing[current]):
            depth[target] = max(depth.get(target, 0), depth[current] + 1)
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)
    # Cyclic nodes are placed in a final deterministic layer, never dropped.
    cyclic = sorted(set(ids) - visited)
    if cyclic:
        final_depth = max(depth.values(), default=-1) + 1
        for identifier in cyclic:
            depth[identifier] = final_depth
    layers_map: dict[int, list[str]] = defaultdict(list)
    for identifier in ids:
        layers_map[depth.get(identifier, 0)].append(identifier)
    layers = tuple(tuple(sorted(layers_map[level])) for level in sorted(layers_map))
    positions: dict[str, Point] = {}
    bounds: dict[str, Rect] = {}
    x = origin.x
    for layer in layers:
        layer_width = max(by_id[i].width for i in layer)
        total_height = sum(by_id[i].height for i in layer) + vertical_gap * max(0, len(layer) - 1)
        y = origin.y - total_height / 2
        for identifier in layer:
            node = by_id[identifier]
            center = Point(round((x + layer_width / 2) / grid) * grid,
                           round((y + node.height / 2) / grid) * grid)
            positions[identifier] = center
            bounds[identifier] = Rect(center.x - node.width / 2, center.y - node.height / 2,
                                       node.width, node.height)
            y += node.height + vertical_gap
        x += layer_width + horizontal_gap
    return TopologyLayout(positions, bounds, layers)
