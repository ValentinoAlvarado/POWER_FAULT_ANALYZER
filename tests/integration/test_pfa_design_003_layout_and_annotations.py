from __future__ import annotations

import json
from pathlib import Path

from examples.canonical_model_scenarios import (
    build_double_bus_substation,
    build_multibus_network,
    build_single_bus_substation,
)
from power_fault_analyzer.application.use_cases.network_workspace import DiagramLabelPlacement
from power_fault_analyzer.diagram.layout import Point, perpendicular_bay_route
from power_fault_analyzer.diagram.model_document_export import render_engineering_svg
from power_fault_analyzer.diagram.model_projection import (
    project_network_to_diagram,
    validate_diagram_document,
)
from power_fault_analyzer.diagram.symbol_catalog import SYMBOL_DEFINITIONS
from power_fault_analyzer.infrastructure.persistence.json_network_document_repository import (
    JSONNetworkDocumentRepository,
)
from power_fault_analyzer.scripting.project import ScriptProject



def test_perpendicular_bay_route_collapses_aligned_default_connection_to_one_segment():
    start = Point(360.0, 220.0)
    end = Point(360.0, 350.0)
    route = perpendicular_bay_route(start, end, 0.0)
    assert route == (start, end)
    assert len(route) - 1 == 1


def test_perpendicular_bay_route_uses_minimum_manhattan_dogleg_after_bar_drag():
    start = Point(380.0, 240.0)
    end = Point(360.0, 350.0)
    route = perpendicular_bay_route(start, end, 0.0)
    assert len(route) == 4
    assert all(abs(first.x - second.x) < 1e-7 or abs(first.y - second.y) < 1e-7
               for first, second in zip(route, route[1:]))
    assert abs(route[0].x - route[1].x) < 1e-7
    assert abs(route[-2].x - route[-1].x) < 1e-7
    route_length = sum(abs(second.x - first.x) + abs(second.y - first.y)
                       for first, second in zip(route, route[1:]))
    lower_bound = abs(end.x - start.x) + abs(end.y - start.y)
    assert abs(route_length - lower_bound) < 1e-7
    assert len(set(route)) == len(route)


def test_perpendicular_bay_route_supports_rotated_bus_axes():
    start = Point(100.0, 100.0)
    end = Point(260.0, 100.0)
    route = perpendicular_bay_route(start, end, 90.0)
    assert route == (start, end)


def test_three_canonical_scenarios_project_without_topology_or_label_errors():
    builders = (build_single_bus_substation, build_double_bus_substation, build_multibus_network)
    for build in builders:
        workspace = build()
        document = project_network_to_diagram(workspace)
        assert validate_diagram_document(workspace, document) == ()
        assert document.equipment_ids == frozenset(item.id for item in workspace.network.equipment)
        assert document.terminal_ids == frozenset(
            terminal.id for equipment in workspace.network.equipment for terminal in equipment.terminals
        )
        assert document.connection_pairs == frozenset(
            (item.terminal_id, item.bus_id) for item in workspace.network.connections
        )
        assert document.diagnostics == ()


def test_path_topology_uses_distinct_bus_rows_and_perpendicular_vertical_bays():
    for build in (build_single_bus_substation, build_multibus_network):
        workspace = build()
        document = project_network_to_diagram(workspace)
        ys = sorted(round(item.center.y, 3) for item in document.buses)
        assert len(ys) == len(document.buses)
        assert all(abs(item.orientation_deg % 180.0) < 1e-6 for item in document.buses)
        assert all(abs((second - first) - 180.0) < 1e-6
                   for first, second in zip(ys, ys[1:]))
        assert len({round(item.center.x, 3) for item in document.buses}) == 2

        equipment_by_id = {item.id: item for item in workspace.network.equipment}
        bus_by_id = {item.bus_id: item for item in document.buses}
        symbols_by_id = {item.equipment_id: item for item in document.symbols}
        for equipment in workspace.network.equipment:
            if len(equipment.terminals) != 2:
                continue
            terminal_buses = [
                next(connection.bus_id for connection in workspace.network.connections
                     if connection.terminal_id == terminal.id)
                for terminal in equipment.terminals
            ]
            assert bus_by_id[terminal_buses[0]].center.y != bus_by_id[terminal_buses[1]].center.y
            assert abs(symbols_by_id[equipment.id].orientation_deg) == 90.0

        # Every branch leaves a horizontal busbar in the perpendicular direction.
        for conductor in document.conductors:
            if len(conductor.points) < 2:
                continue
            first, second = conductor.points[:2]
            penultimate, terminal = conductor.points[-2:]
            assert abs(first.x - second.x) < 1e-6
            assert abs(penultimate.x - terminal.x) < 1e-6



def test_explicit_double_bus_feeder_bars_are_horizontal_with_centered_labels():
    workspace = build_double_bus_substation()
    document = project_network_to_diagram(workspace)
    buses = {item.name: item for item in document.buses}
    labels = {(item.owner_id, item.text): item for item in document.labels}
    for name in ("BUS-A", "BUS-B", "FEEDER-A", "FEEDER-B"):
        assert abs(buses[name].orientation_deg % 180.0) < 1e-6
    for name in ("BUS-A", "BUS-B", "FEEDER-A", "FEEDER-B"):
        label = labels[(buses[name].bus_id, name)]
        assert label.anchor == "start"
        assert label.position.x > buses[name].bounds.right



def test_all_canonical_scenarios_keep_branch_equipment_out_of_the_busbar_axis():
    for build in (build_single_bus_substation, build_double_bus_substation,
                  build_multibus_network):
        workspace = build()
        document = project_network_to_diagram(workspace)
        buses = {item.bus_id: item for item in document.buses}
        symbols = {item.equipment_id: item for item in document.symbols}
        assert len({round(item.center.y, 3) for item in document.buses}) == len(document.buses)
        for equipment in workspace.network.equipment:
            if len(equipment.terminals) != 2:
                continue
            projected = symbols[equipment.id]
            assert abs(projected.orientation_deg) == 90.0, equipment.name
            connected = [
                next(link.bus_id for link in workspace.network.connections
                     if link.terminal_id == terminal.id)
                for terminal in equipment.terminals
            ]
            assert buses[connected[0]].center.y != buses[connected[1]].center.y
        for conductor in document.conductors:
            if len(conductor.points) < 2:
                continue
            start, first_bend = conductor.points[:2]
            last_bend, end = conductor.points[-2:]
            bus = buses[conductor.bus_id]
            if abs(bus.orientation_deg % 180.0) < 1e-6:
                assert abs(start.x - first_bend.x) < 1e-6
                assert abs(last_bend.x - end.x) < 1e-6


def test_bus_incidence_allocates_distinct_perpendicular_bay_taps():
    for build in (build_single_bus_substation, build_double_bus_substation,
                  build_multibus_network):
        workspace = build()
        document = project_network_to_diagram(workspace)
        taps_by_bus = {}
        for conductor in document.conductors:
            taps_by_bus.setdefault(conductor.bus_id, []).append(conductor.points[0])
        for bus_id, taps in taps_by_bus.items():
            unique = {(round(point.x, 4), round(point.y, 4)) for point in taps}
            assert len(unique) == len(taps), f"duplicate physical bays on bus {bus_id}"
            bus = next(item for item in document.buses if item.bus_id == bus_id)
            assert all(abs(point.y - bus.center.y) < 1e-6 for point in taps)
            assert all(bus.bounds.x <= point.x <= bus.bounds.right for point in taps)


def test_svg_keeps_terminal_ids_symbol_provenance_and_editable_text_nodes():
    workspace = build_single_bus_substation()
    document = project_network_to_diagram(workspace)
    svg = render_engineering_svg(document, width_mm=180, height_mm=92)
    assert 'id="conductors"' in svg and 'id="equipment"' in svg and 'id="annotations"' in svg
    assert 'data-terminal-id="' in svg
    assert 'data-definition-sha256="' in svg
    assert 'data-normative-status="NOT_VERIFIED"' in svg
    assert 'id="' in svg and '<text' in svg
    assert "LINE-01†" in svg and "GRID-EQUIVALENT‡" in svg
    assert "Equipment parameters unresolved" in svg
    assert "Sequence-network data incomplete" in svg
    assert 'stroke-width="' in svg and "PFA-SLD-CB-001" in svg


def test_equipment_labels_remain_local_to_their_symbols_after_collision_resolution():
    workspace = build_single_bus_substation()
    document = project_network_to_diagram(workspace)
    labels_by_owner = {item.owner_id: item for item in document.labels if item.owner_id is not None}
    for symbol in document.symbols:
        label = labels_by_owner[symbol.equipment_id]
        distance = ((label.position.x - symbol.center.x) ** 2 +
                    (label.position.y - symbol.center.y) ** 2) ** 0.5
        assert distance < 100.0, (symbol.name, label.position, symbol.center, distance)



def test_publication_presets_emit_exact_physical_dimensions():
    workspace = build_single_bus_substation()
    document = project_network_to_diagram(workspace)
    double_column = render_engineering_svg(document, preset="double-column")
    landscape = render_engineering_svg(document, preset="landscape")
    single_column = render_engineering_svg(document, preset="single-column")
    assert 'width="180mm" height="120mm"' in double_column
    assert 'width="180mm" height="92mm"' in landscape
    assert 'width="88mm" height="62mm"' in single_column

def test_symbol_catalog_has_stable_provenance_and_does_not_claim_iec_conformity():
    symbol_ids = [item.symbol_id for item in SYMBOL_DEFINITIONS]
    hashes = [item.definition_hash for item in SYMBOL_DEFINITIONS]
    assert len(symbol_ids) == len(set(symbol_ids))
    assert len(hashes) == len(set(hashes))
    assert all(len(value) == 64 for value in hashes)
    assert all(item.normative_status == "NOT_VERIFIED" for item in SYMBOL_DEFINITIONS)
    assert all(
        "cross-reference pending" in item.standard_reference
        for item in SYMBOL_DEFINITIONS if item.family != "transformer"
    )
    transformer = next(item for item in SYMBOL_DEFINITIONS if item.family == "transformer")
    assert "IEC 60617 S00841 Form 1" in transformer.standard_reference
    assert "dimensional conformance NOT_VERIFIED" in transformer.standard_reference


def test_independent_diagram_labels_round_trip_in_schema_15_without_touching_network(tmp_path: Path):
    workspace = build_single_bus_substation()
    canonical_connection_count = len(workspace.network.connections)
    bus = workspace.network.buses[0]
    label = DiagramLabelPlacement.create(
        "Figure 1 — source equivalent", 310.0, 185.0, owner_id=bus.id,
        anchor="start", font_family="STIX Two Text", size_pt=8.5,
        weight="semibold", color="#1D4ED8", rotation_deg=0.0,
        layer="annotations", priority=5,
    )
    workspace.upsert_diagram_label(label)
    repository = JSONNetworkDocumentRepository()
    path = repository.save(workspace, tmp_path / "design-003.network.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "1.5"
    loaded = repository.load(path)
    restored = loaded.diagram_labels[label.label_id]
    assert restored == label
    assert restored.color == "#1D4ED8"
    assert len(loaded.network.connections) == canonical_connection_count
    rendered = project_network_to_diagram(loaded)
    projected_label = next(item for item in rendered.labels if item.label_id == label.label_id)
    assert projected_label.text == label.text and projected_label.color == "#1D4ED8"


def test_schema_14_documents_remain_readable_after_label_schema_migration(tmp_path: Path):
    workspace = build_double_bus_substation()
    repository = JSONNetworkDocumentRepository()
    path = repository.save(workspace, tmp_path / "schema-14-source.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["schema_version"] = "1.4"
    payload["diagram"].pop("labels", None)
    path.write_text(json.dumps(payload), encoding="utf-8")
    loaded = repository.load(path)
    assert loaded.network.id == workspace.network.id
    assert loaded.diagram_labels == {}


def test_code_automation_uses_same_workspace_and_annotation_model():
    project = ScriptProject("Code and Automation label test")
    bus = project.add_bus("BUS-A", 13.8, x=400.0, y=220.0)
    label = project.set_diagram_label(
        bus, "bus-name", "MAIN BUS A", x=420.0, y=180.0,
        anchor="start", size_pt=8.0, weight="bold", color="#1D4ED8",
    )
    workspace = project.render()
    document = project_network_to_diagram(workspace)
    projected = next(item for item in document.labels if item.label_id == label.label_id)
    assert projected.text == "MAIN BUS A"
    assert projected.color == "#1D4ED8"
    assert workspace.diagram_labels[label.label_id] is label


def test_qgraphicsobject_symbol_signal_contract_is_not_branch_carrier_backed():
    """Guard the QObject-vs-QGraphicsItem signal ownership distinction without Qt."""
    import ast

    source = (Path(__file__).resolve().parents[2] / "src" / "power_fault_analyzer" /
              "interfaces" / "desktop" / "workbench" / "network_canvas.py")
    tree = ast.parse(source.read_text(encoding="utf-8"))
    classes = {node.name: node for node in tree.body if isinstance(node, ast.ClassDef)}

    for name in ("BusSymbol", "CanonicalEquipmentSymbol", "SourceSymbol"):
        node = classes[name]
        init = next(item for item in node.body
                    if isinstance(item, ast.FunctionDef) and item.name == "__init__")
        item_change = next(item for item in node.body
                           if isinstance(item, ast.FunctionDef) and item.name == "itemChange")
        initializers = []
        for statement in init.body:
            if not isinstance(statement, ast.Assign) or not isinstance(statement.value, ast.Constant):
                continue
            for target in statement.targets:
                if (isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name)
                        and target.value.id == "self" and target.attr == "_initializing"):
                    initializers.append((target.attr, statement.value.value))
        # Both guard states must be assigned during construction.
        assert ("_initializing", True) in initializers
        assert ("_initializing", False) in initializers

        called_native_signal = any(
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute) and call.func.attr == "emit"
            and isinstance(call.func.value, ast.Attribute) and call.func.value.attr == "moved"
            and isinstance(call.func.value.value, ast.Name) and call.func.value.value.id == "self"
            for call in ast.walk(item_change)
        )
        assert called_native_signal, name
        assert not any(
            isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
            and node.value.id == "self" and node.attr == "_branch_signals"
            for node in ast.walk(item_change)
        ), name


def test_busbar_lengths_follow_canonical_terminal_incidence_not_neighbour_degree():
    from power_fault_analyzer.diagram.model_projection import _busbar_length

    builders = (build_single_bus_substation, build_double_bus_substation, build_multibus_network)
    for build in builders:
        workspace = build()
        document = project_network_to_diagram(workspace)
        terminal_counts = {bus.id: 0 for bus in workspace.network.buses}
        for connection in workspace.network.connections:
            terminal_counts[connection.bus_id] += 1
        for bus in document.buses:
            expected = _busbar_length(terminal_counts[bus.bus_id])
            assert bus.length == expected
            assert 160.0 <= bus.length <= 280.0


def test_symbol_catalogue_marks_breaker_and_disconnector_as_distinct_candidates():
    from power_fault_analyzer.diagram.symbol_catalog import get_symbol_definition

    breaker = get_symbol_definition("circuit_breaker")
    disconnector = get_symbol_definition("disconnector")
    assert breaker.symbol_id != disconnector.symbol_id
    assert "07-13-05" in breaker.standard_reference
    assert "07-13-06" in disconnector.standard_reference
    assert "NOT_VERIFIED" == breaker.normative_status == disconnector.normative_status
    assert "cross" in breaker.visual_description.lower()
    assert "bar" in disconnector.visual_description.lower()


def test_svg_renders_distinct_function_marks_for_breaker_and_disconnector():
    from power_fault_analyzer.diagram.layout import Point, Rect
    from power_fault_analyzer.diagram.svg_export import SvgSymbol, render_svg

    symbols = (
        SvgSymbol("circuit_breaker", Point(40, 50), 44, 28, "CB", "open"),
        SvgSymbol("disconnector", Point(120, 50), 44, 28, "DS", "open"),
    )
    rendered = render_svg(
        width_mm=120, height_mm=60, symbols=symbols,
        view_box=Rect(0, 0, 180, 90),
    )
    assert 'class="breaker-function-mark"' in rendered
    assert 'data-function-mark="iec-60617-07-13-05-candidate"' in rendered
    assert 'class="disconnector-function-mark"' in rendered
    assert 'data-function-mark="iec-60617-07-13-06-candidate"' in rendered


def test_model_export_marks_only_explicit_canonical_bus_taps():
    from power_fault_analyzer.diagram.model_document_export import render_engineering_svg

    workspace = build_multibus_network()
    document = project_network_to_diagram(workspace)
    svg = render_engineering_svg(document)
    # Every exported marker is derived from a canonical terminal-to-bus record;
    # no graphical crossing is promoted into an electrical junction.
    expected_unique_taps = {
        (round(item.points[0].x, 4), round(item.points[0].y, 4))
        for item in document.conductors if item.points
    }
    assert svg.count('data-symbol-id="PFA-TOPOLOGY-JUNCTION-001"') == len(expected_unique_taps)


def test_default_bay_routes_are_straight_and_perpendicular_from_busbars():
    """Canonical layouts use shared bay lanes instead of needless orthogonal jogs."""
    builders = (build_single_bus_substation, build_double_bus_substation, build_multibus_network)
    for build in builders:
        workspace = build()
        document = project_network_to_diagram(workspace)
        bus_by_id = {item.bus_id: item for item in document.buses}
        symbol_by_terminal = {
            terminal_id: symbol
            for symbol in document.symbols
            for terminal_id in symbol.terminal_ids
        }
        taps_by_bus = {}
        for conductor in document.conductors:
            bus = bus_by_id[conductor.bus_id]
            assert len(conductor.points) == 2, (
                "Default canonical bay should connect by one straight segment",
                conductor.terminal_id,
                conductor.points,
            )
            start, end = conductor.points
            if abs(bus.orientation_deg % 180.0) < 1e-6:
                assert start.x == end.x
                assert start.y == bus.center.y
            else:
                assert start.y == end.y
                assert start.x == bus.center.x
            taps_by_bus.setdefault(conductor.bus_id, []).append(start)
            symbol = symbol_by_terminal[conductor.terminal_id]
            assert end in symbol.terminal_points
        for bus_id, taps in taps_by_bus.items():
            assert len(taps) == len(set(taps)), f"Duplicate tap on bus {bus_id}: {taps}"


def test_two_terminal_bay_uses_one_shared_bus_lane_at_both_ends():
    builders = (build_single_bus_substation, build_double_bus_substation, build_multibus_network)
    for build in builders:
        workspace = build()
        document = project_network_to_diagram(workspace)
        conductors = {item.terminal_id: item for item in document.conductors}
        symbols = {item.equipment_id: item for item in document.symbols}
        connected_bus = {item.terminal_id: item.bus_id for item in workspace.network.connections}
        for equipment in workspace.network.equipment:
            terminals = tuple(equipment.terminals)
            if len(terminals) != 2 or connected_bus[terminals[0].id] == connected_bus[terminals[1].id]:
                continue
            first = conductors[terminals[0].id].points
            second = conductors[terminals[1].id].points
            # With automatically composed horizontal busbars, both terminal
            # taps share the same X lane and the equipment lies on that axis.
            assert first[0].x == second[0].x
            symbol = symbols[equipment.id]
            assert symbol.center.x == first[0].x
            assert symbol.center.x == second[0].x


def test_shortest_orthogonal_route_respects_perpendicular_departure_and_arrival():
    from power_fault_analyzer.diagram.layout import Point, Rect
    from power_fault_analyzer.diagram.model_projection import EngineeringBus, _route_to_terminal

    bus = EngineeringBus(
        bus_id=__import__("uuid").uuid4(), name="BUS", nominal_voltage_kv=13.8,
        bounds=Rect(0.0, -3.0, 200.0, 6.0), center=Point(100.0, 0.0),
        orientation_deg=0.0,
    )
    aligned = _route_to_terminal(Point(120.0, 0.0), Point(120.0, 100.0), bus)
    assert aligned == (Point(120.0, 0.0), Point(120.0, 100.0))

    offset = _route_to_terminal(Point(100.0, 0.0), Point(140.0, 100.0), bus)
    assert offset[1].x == offset[0].x  # perpendicular departure from busbar
    assert offset[-1].x == offset[-2].x  # axial arrival at vertical bay pin
    actual = sum(
        abs(second.x - first.x) + abs(second.y - first.y)
        for first, second in zip(offset, offset[1:])
    )
    direct_lower_bound = abs(offset[-1].x - offset[0].x) + abs(offset[-1].y - offset[0].y)
    assert actual == direct_lower_bound
