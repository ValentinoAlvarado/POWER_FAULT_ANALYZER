"""Grid-based Manhattan routing with obstacle avoidance.

This module operates on drawing geometry only. It never infers electrical
connectivity; callers provide explicit terminal points and obstacle envelopes.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from math import hypot
from typing import Iterable

from .layout import Point, Rect, snap_point


@dataclass(frozen=True, slots=True)
class RouteResult:
    points: tuple[Point, ...]
    bends: int
    length: float


def snap_to_terminal(point: Point, terminals: Iterable[Point], tolerance: float) -> Point:
    if tolerance < 0:
        raise ValueError("tolerance cannot be negative")
    candidates = [(hypot(point.x - t.x, point.y - t.y), t) for t in terminals]
    if not candidates:
        return point
    distance, terminal = min(candidates, key=lambda item: item[0])
    return terminal if distance <= tolerance else point


def _compress(points: list[Point]) -> tuple[Point, ...]:
    if len(points) < 3:
        return tuple(points)
    result = [points[0]]
    for index in range(1, len(points) - 1):
        a, b, c = result[-1], points[index], points[index + 1]
        if (a.x == b.x == c.x) or (a.y == b.y == c.y):
            continue
        result.append(b)
    result.append(points[-1])
    return tuple(result)


def route_orthogonal_avoiding(
    start: Point, end: Point, obstacles: Iterable[Rect], *,
    grid: float = 20.0, clearance: float = 8.0, max_nodes: int = 50000,
) -> RouteResult:
    """Find a shortest four-neighbour route on a regular grid using BFS.

    The search is bounded. An explicit failure is returned as ValueError rather
    than silently drawing a conductor through an equipment envelope.
    """
    if grid <= 0 or clearance < 0 or max_nodes < 1:
        raise ValueError("grid, clearance and max_nodes must be positive.")
    blocked = tuple(obstacles)
    s, e = snap_point(start, grid), snap_point(end, grid)
    if s == e:
        return RouteResult((s,), 0, 0.0)

    def free(p: Point) -> bool:
        if p == s or p == e:
            return True
        probe = Rect(p.x - clearance / 2, p.y - clearance / 2,
                     max(clearance, 0.01), max(clearance, 0.01))
        return not any(probe.intersects(rect) for rect in blocked)

    # Search bounds include a deterministic margin around endpoints/obstacles.
    xs = [s.x, e.x]
    ys = [s.y, e.y]
    for rect in blocked:
        xs.extend((rect.x - grid, rect.right + grid))
        ys.extend((rect.y - grid, rect.bottom + grid))
    margin = 12 * grid
    min_x, max_x = min(xs) - margin, max(xs) + margin
    min_y, max_y = min(ys) - margin, max(ys) + margin
    start_key, end_key = (round(s.x / grid), round(s.y / grid)), (round(e.x / grid), round(e.y / grid))
    queue = deque([start_key])
    previous: dict[tuple[int, int], tuple[int, int] | None] = {start_key: None}
    directions = ((1, 0), (0, 1), (-1, 0), (0, -1))
    while queue and len(previous) <= max_nodes:
        current = queue.popleft()
        if current == end_key:
            break
        for dx, dy in directions:
            nxt = (current[0] + dx, current[1] + dy)
            p = Point(nxt[0] * grid, nxt[1] * grid)
            if nxt in previous or not (min_x <= p.x <= max_x and min_y <= p.y <= max_y):
                continue
            if free(p):
                previous[nxt] = current
                queue.append(nxt)
    if end_key not in previous:
        raise ValueError("No collision-free orthogonal route found within search limit.")
    keys = []
    cursor = end_key
    while cursor is not None:
        keys.append(cursor)
        cursor = previous[cursor]
    keys.reverse()
    raw = [Point(x * grid, y * grid) for x, y in keys]
    points = _compress(raw)
    length = sum(hypot(b.x - a.x, b.y - a.y) for a, b in zip(points, points[1:]))
    return RouteResult(points, max(0, len(points) - 2), length)
