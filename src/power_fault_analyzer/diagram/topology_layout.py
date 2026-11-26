"""Deterministic topology-aware diagram layout from explicit graph relationships."""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Iterable

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


def layout_topology(
    nodes: Iterable[LayoutNode], edges: Iterable[LayoutEdge], *,
    origin: Point = Point(80.0, 80.0), grid: float = 20.0,
    horizontal_gap: float = 120.0, vertical_gap: float = 100.0,
) -> TopologyLayout:
    """Layer a directed drawing graph; cycles are handled deterministically.

    Edges describe visual/logical relationships supplied by the caller. They are
    not electrical connections unless built from the canonical network model.
    """
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
