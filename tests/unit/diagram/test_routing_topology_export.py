from power_fault_analyzer.diagram import (
    LayoutEdge, LayoutNode, Point, Rect, SvgLabel, SvgMetadata, SvgPath, SvgSymbol,
    layout_topology, render_svg, route_orthogonal_avoiding, snap_to_terminal,
)


def test_terminal_snap_uses_nearest_explicit_terminal():
    terminals = (Point(0, 0), Point(100, 0))
    assert snap_to_terminal(Point(96, 2), terminals, 10) == Point(100, 0)
    assert snap_to_terminal(Point(96, 2), terminals, 2) == Point(96, 2)


def test_router_avoids_obstacle_and_returns_orthogonal_path():
    obstacle = Rect(40, -20, 40, 40)
    route = route_orthogonal_avoiding(Point(0, 0), Point(120, 0), [obstacle],
                                      grid=20, clearance=10)
    assert route.points[0] == Point(0, 0)
    assert route.points[-1] == Point(120, 0)
    assert route.bends >= 2
    for a, b in zip(route.points, route.points[1:]):
        assert a.x == b.x or a.y == b.y
    assert all(not Rect(p.x-4, p.y-4, 8, 8).intersects(obstacle)
               for p in route.points[1:-1])


def test_router_reports_impossible_bounded_route():
    import pytest
    with pytest.raises(ValueError, match="No collision-free"):
        route_orthogonal_avoiding(Point(0, 0), Point(100, 0),
                                  [Rect(-300, -300, 700, 700)],
                                  grid=20, max_nodes=200)


def test_topology_layout_respects_graph_layers_and_grid():
    nodes = [LayoutNode("G", 60, 60, "generator"),
             LayoutNode("B1", 100, 10, "busbar"),
             LayoutNode("T", 60, 80, "transformer"),
             LayoutNode("B2", 100, 10, "busbar")]
    edges = [LayoutEdge("G", "B1", "e1"), LayoutEdge("B1", "T", "e2"),
             LayoutEdge("T", "B2", "e3")]
    result = layout_topology(nodes, edges, grid=20)
    assert result.layers == (("G",), ("B1",), ("T",), ("B2",))
    assert result.positions["G"].x < result.positions["B1"].x < result.positions["T"].x
    assert result.positions["G"].x % 20 == 0


def test_topology_layout_keeps_cycles_in_deterministic_final_layer():
    nodes = [LayoutNode("A"), LayoutNode("B"), LayoutNode("C")]
    edges = [LayoutEdge("A", "B", "ab"), LayoutEdge("B", "A", "ba")]
    first = layout_topology(nodes, edges)
    second = layout_topology(nodes, edges)
    assert first == second
    assert set(first.positions) == {"A", "B", "C"}


def test_svg_export_is_physical_vector_and_escapes_metadata():
    svg = render_svg(
        width_mm=180, height_mm=90,
        symbols=[SvgSymbol("transformer", Point(100, 80), 42, 70, "T1")],
        paths=[SvgPath((Point(10, 80), Point(79, 80), Point(79, 140)))],
        labels=[SvgLabel("T1 & feeder", Point(100, 35))],
        metadata=SvgMetadata("Test <diagram>", "Engineer", "PFA", "R1", "vector output"),
    )
    assert 'width="180mm"' in svg and 'height="90mm"' in svg
    assert "<title>Test &lt;diagram&gt;</title>" in svg
    assert "id=\"conductors\"" in svg and "id=\"equipment\"" in svg
    assert "T1 &amp; feeder" in svg
    assert "<path" in svg and "<circle" in svg
