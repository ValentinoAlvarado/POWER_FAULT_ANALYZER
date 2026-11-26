from __future__ import annotations

import math
import xml.etree.ElementTree as ET

from examples.canonical_model_scenarios import build_single_bus_substation
from power_fault_analyzer.diagram.model_document_export import render_engineering_svg
from power_fault_analyzer.diagram.model_projection import project_network_to_diagram
from power_fault_analyzer.diagram.symbol_catalog import get_symbol_definition


def test_two_winding_transformer_geometry_has_real_circle_overlap_and_external_leads():
    definition = get_symbol_definition("transformer")
    circles = [item for item in definition.primitives if item.kind == "circle"]
    leads = [item for item in definition.primitives if item.kind == "line"]

    assert len(circles) == 2
    assert len(leads) == 2
    first_x, first_y, first_radius = circles[0].coordinates
    second_x, second_y, second_radius = circles[1].coordinates
    center_distance = math.hypot(second_x - first_x, second_y - first_y)
    assert center_distance < first_radius + second_radius
    assert math.isclose(first_radius, second_radius)
    assert math.isclose(first_radius + second_radius - center_distance, 12.0)

    # The two short external leads end exactly at the outer circle boundaries.
    left = next(item for item in leads if item.terminal_index == 0)
    right = next(item for item in leads if item.terminal_index == 1)
    assert left.coordinates == (-34.0, 0.0, -26.0, 0.0)
    assert right.coordinates == (26.0, 0.0, 34.0, 0.0)
    assert [(item.designation, item.x, item.y) for item in definition.terminals] == [
        ("HV", -34.0, 0.0), ("LV", 34.0, 0.0)
    ]


def test_transformer_symbol_reference_is_traceable_but_not_falsely_certified():
    definition = get_symbol_definition("transformer")
    assert definition.standard_reference.startswith("IEC 60617 S00841 Form 1")
    assert "S00842" in definition.standard_edition
    assert "IEC60617_Snapshot_2019-03-05.pdf" in definition.source_uri
    assert definition.normative_status == "NOT_VERIFIED"
    assert "no IEC artwork copied" in definition.provenance
    assert len(definition.definition_hash) == 64


def test_transformer_svg_uses_two_overlapping_unfilled_circles_and_terminal_leads():
    workspace = build_single_bus_substation()
    document = project_network_to_diagram(workspace)
    svg = render_engineering_svg(document, width_mm=180.0, height_mm=120.0)
    root = ET.fromstring(svg)
    namespace = {"svg": "http://www.w3.org/2000/svg"}
    group = next(
        item for item in root.findall(".//svg:g", namespace)
        if item.attrib.get("data-symbol-id") == "PFA-SLD-TRANSFORMER-2W-001"
    )
    circles = group.findall("svg:circle[@class='symbol-winding']", namespace)
    leads = group.findall("svg:path[@class='symbol-terminal-lead']", namespace)
    assert len(circles) == 2
    assert len(leads) == 2
    assert all(item.attrib.get("fill") == "none" for item in circles)
    centres = [(float(item.attrib["cx"]), float(item.attrib["cy"])) for item in circles]
    radii = [float(item.attrib["r"]) for item in circles]
    assert math.dist(*centres) < sum(radii)
    transformer = next(item for item in document.symbols if item.family == "transformer")
    assert {item.attrib.get("data-terminal-id") for item in leads} == {
        str(identifier) for identifier in transformer.terminal_ids
    }
    assert {item.attrib.get("data-terminal") for item in leads} == set(
        transformer.terminal_designations
    )


def test_transformer_is_projected_as_vertical_two_terminal_bay_with_leads_on_its_axis():
    document = project_network_to_diagram(build_single_bus_substation())
    transformer = next(item for item in document.symbols if item.family == "transformer")
    assert abs(abs(transformer.orientation_deg) - 90.0) < 1e-9
    assert len(transformer.terminal_points) == 2
    assert math.isclose(transformer.terminal_points[0].x, transformer.center.x, abs_tol=1e-7)
    assert math.isclose(transformer.terminal_points[1].x, transformer.center.x, abs_tol=1e-7)
    assert transformer.terminal_points[0].y < transformer.center.y
    assert transformer.terminal_points[1].y > transformer.center.y
