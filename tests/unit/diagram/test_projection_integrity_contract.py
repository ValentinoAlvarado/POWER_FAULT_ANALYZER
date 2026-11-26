from __future__ import annotations

from dataclasses import replace

import pytest

from examples.canonical_model_scenarios import (
    build_double_bus_substation,
    build_multibus_network,
    build_single_bus_substation,
)
from power_fault_analyzer.diagram.model_projection import (
    project_network_to_diagram,
    validate_diagram_document,
)

BUILDERS = (
    build_single_bus_substation,
    build_double_bus_substation,
    build_multibus_network,
)


@pytest.mark.parametrize("build", BUILDERS, ids=("single-bus", "double-bus", "multibus"))
def test_canonical_projection_is_an_exact_model_projection(build):
    workspace = build()
    document = project_network_to_diagram(workspace)
    assert validate_diagram_document(workspace, document) == ()


@pytest.mark.parametrize("build", BUILDERS, ids=("single-bus", "double-bus", "multibus"))
def test_validator_rejects_duplicate_conductor_even_when_connection_pair_set_is_unchanged(build):
    workspace = build()
    document = project_network_to_diagram(workspace)
    malformed = replace(document, conductors=(*document.conductors, document.conductors[0]))

    errors = validate_diagram_document(workspace, malformed)

    assert "duplicate conductor terminal projection" in errors
    assert "conductor/connection cardinality mismatch" in errors


def test_validator_rejects_conductor_attached_to_a_different_canonical_bus():
    workspace = build_double_bus_substation()
    document = project_network_to_diagram(workspace)
    conductor = document.conductors[0]
    wrong_bus = next(bus.bus_id for bus in document.buses if bus.bus_id != conductor.bus_id)
    malformed_conductor = replace(conductor, bus_id=wrong_bus)
    malformed = replace(
        document,
        conductors=(malformed_conductor, *document.conductors[1:]),
    )

    errors = validate_diagram_document(workspace, malformed)

    assert any(item.startswith("conductor connected to wrong bus:") for item in errors)
    assert "terminal/connection mismatch" in errors


def test_validator_rejects_a_symbol_that_claims_another_equipments_terminal():
    workspace = build_single_bus_substation()
    document = project_network_to_diagram(workspace)
    first, second, *remaining = document.symbols
    wrong_terminal = second.terminal_ids[0]
    malformed_first = replace(first, terminal_ids=(wrong_terminal,))
    malformed = replace(document, symbols=(malformed_first, second, *remaining))

    errors = validate_diagram_document(workspace, malformed)

    assert "duplicate terminal in symbol projection" in errors
    assert any(item.startswith("symbol terminal ownership mismatch:") for item in errors)


def test_validator_rejects_duplicate_bus_projection_identity():
    workspace = build_multibus_network()
    document = project_network_to_diagram(workspace)
    malformed = replace(document, buses=(*document.buses, document.buses[0]))

    errors = validate_diagram_document(workspace, malformed)

    assert "duplicate bus projection identity" in errors
    assert "bus projection mismatch" in errors


def test_validator_rejects_conductor_whose_tap_is_outside_the_physical_busbar():
    workspace = build_single_bus_substation()
    document = project_network_to_diagram(workspace)
    conductor = document.conductors[0]
    bus = next(item for item in document.buses if item.bus_id == conductor.bus_id)
    outside = replace(conductor.points[0], x=bus.bounds.right + 100.0)
    points = (outside, *conductor.points[1:])
    malformed = replace(
        document,
        conductors=(replace(conductor, points=points), *document.conductors[1:]),
    )

    errors = validate_diagram_document(workspace, malformed)

    assert any(item.startswith("conductor tap is outside its busbar:") for item in errors)
