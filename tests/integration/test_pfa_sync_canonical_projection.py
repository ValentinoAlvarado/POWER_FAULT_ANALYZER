from __future__ import annotations

import pytest

from examples.canonical_model_scenarios import (
    build_double_bus_substation,
    build_multibus_network,
    build_single_bus_substation,
)
from power_fault_analyzer.diagram.model_document_export import render_engineering_svg
from power_fault_analyzer.diagram.model_projection import (
    DiagramProjectionError,
    project_network_to_diagram,
    validate_diagram_document,
)
from power_fault_analyzer.infrastructure.persistence.json_network_document_repository import (
    JSONNetworkDocumentRepository,
)
from power_fault_analyzer.scripting.worker_client import ScriptWorkerError, run_script_worker


@pytest.mark.parametrize("builder", [
    build_single_bus_substation, build_double_bus_substation, build_multibus_network,
])
def test_canonical_scenario_projection_is_bijective_and_persistent(builder, tmp_path):
    repository = JSONNetworkDocumentRepository()
    workspace = builder()
    document = project_network_to_diagram(workspace)

    assert validate_diagram_document(workspace, document) == ()
    assert document.equipment_ids == frozenset(item.id for item in workspace.network.equipment)
    assert document.connection_pairs == frozenset(
        (item.terminal_id, item.bus_id) for item in workspace.network.connections
    )
    assert document.terminal_ids == frozenset(
        terminal.id for equipment in workspace.network.equipment for terminal in equipment.terminals
    )

    before_model = {
        "buses": tuple((item.id, item.nominal_voltage.value_kv) for item in workspace.network.buses),
        "equipment": tuple((item.id, item.name, tuple(t.id for t in item.terminals))
                           for item in workspace.network.equipment),
        "connections": document.connection_pairs,
    }
    target = repository.save(workspace, tmp_path / "canonical.network.json")
    reopened = repository.load(target)
    regenerated = project_network_to_diagram(reopened)

    assert validate_diagram_document(reopened, regenerated) == ()
    assert regenerated.connection_pairs == document.connection_pairs
    assert regenerated.equipment_ids == document.equipment_ids
    after_model = {
        "buses": tuple((item.id, item.nominal_voltage.value_kv) for item in reopened.network.buses),
        "equipment": tuple((item.id, item.name, tuple(t.id for t in item.terminals))
                           for item in reopened.network.equipment),
        "connections": regenerated.connection_pairs,
    }
    assert after_model == before_model
    svg = render_engineering_svg(regenerated)
    assert 'width="180mm"' in svg
    assert 'id="conductors"' in svg and 'id="equipment"' in svg
    assert "Generated from canonical POWER_FAULT_ANALYZER Network model." in svg


def test_geometry_mutation_does_not_change_electrical_model():
    workspace = build_single_bus_substation()
    before = (workspace.network.buses, workspace.network.equipment, workspace.network.connections)
    workspace.diagram_positions.update({
        workspace.network.buses[0].id: (999.0, 777.0),
    })
    document = project_network_to_diagram(workspace)
    after = (workspace.network.buses, workspace.network.equipment, workspace.network.connections)
    assert before == after
    assert validate_diagram_document(workspace, document) == ()


def test_projection_rejects_unconnected_equipment_terminal():
    workspace = build_single_bus_substation()
    equipment = workspace.network.equipment[0]
    terminal_id = equipment.terminals[0].id
    workspace.network.disconnect(terminal_id)
    with pytest.raises(DiagramProjectionError, match="unconnected terminal"):
        project_network_to_diagram(workspace)


def test_script_worker_returns_canonical_workspace_json():
    result = run_script_worker(
        'project = ScriptProject("Worker API integration")\n'
        'bus = project.add_bus("BUS-W", voltage_kv=13.8)\n'
        'workspace = project.render()\n'
    )
    assert result["ok"] is True
    assert result["project_name"] == "Worker API integration"
    assert len(result["document"]["network"]["buses"]) == 1


def test_script_worker_rejects_imports_and_file_access():
    with pytest.raises(ScriptWorkerError, match="Imports are disabled"):
        run_script_worker('import os\nproject = ScriptProject("blocked")')
    with pytest.raises(ScriptWorkerError, match="Call to 'open'"):
        run_script_worker('project = ScriptProject("blocked")\nopen("x", "w")')


def test_persisted_equipment_label_and_placement_are_used_by_projection(tmp_path):
    from power_fault_analyzer.application.use_cases.network_workspace import DiagramSymbolPlacement
    workspace = build_single_bus_substation()
    equipment = next(item for item in workspace.network.equipment if item.name == "CB-01")
    placement = DiagramSymbolPlacement.create(
        "IEC-CIRCUIT-BREAKER", 700.0, 360.0, 90.0,
        equipment_id=equipment.id, label="INCOMER BREAKER",
    )
    workspace.diagram_symbols[placement.instance_id] = placement
    repository = JSONNetworkDocumentRepository()
    loaded = repository.load(repository.save(workspace, tmp_path / "label.network.json"))
    document = project_network_to_diagram(loaded)
    symbol = next(item for item in document.symbols if item.equipment_id == equipment.id)
    label = next(item for item in document.labels if item.owner_id == equipment.id)
    assert symbol.center.x == 700.0 and symbol.center.y == 360.0
    assert symbol.orientation_deg == 90.0
    assert label.text == "INCOMER BREAKER"


def test_async_script_worker_can_be_cancelled_by_timeout():
    import asyncio

    from power_fault_analyzer.scripting.worker_client import run_script_worker_async

    async def exercise():
        with pytest.raises(asyncio.TimeoutError):
            await run_script_worker_async(
                'project = ScriptProject("cancel")\nwhile True:\n    pass',
                timeout_seconds=0.25,
            )
    asyncio.run(exercise())


def test_topology_placeholders_and_incomplete_source_sequences_block_studies():
    from power_fault_analyzer.domain.services.network_validation_service import (
        DefaultNetworkValidationService,
    )
    workspace = build_single_bus_substation()
    diagnostics = DefaultNetworkValidationService().validate_for_calculation(workspace.network)
    error_codes = {item.code for item in diagnostics if item.severity.value == "error"}
    assert "NET-EQUIPMENT-MODEL-UNRESOLVED" in error_codes
    source = next(item for item in workspace.network.equipment if item.name == "GRID-EQUIVALENT")
    evidence = {item.name: item for item in source.parameters}
    assert evidence["z1_resistance_pu"].value == 0.08
    assert evidence["z1_reactance_pu"].value == 0.24
    assert evidence["prefault_voltage_pu"].value is None
    assert evidence["z2_pu"].value is None and evidence["z0_pu"].value is None


def test_canonical_svg_and_pdf_are_vector_exports_with_technical_switch_symbol(tmp_path):
    from power_fault_analyzer.diagram.model_document_export import (
        export_engineering_pdf,
        export_engineering_svg,
    )
    workspace = build_single_bus_substation()
    document = project_network_to_diagram(workspace)
    svg_path = export_engineering_svg(document, tmp_path / "single-bus.svg",
                                      width_mm=180, height_mm=92)
    svg = svg_path.read_text(encoding="utf-8")
    assert 'id="conductors"' in svg
    assert 'id="equipment"' in svg
    assert "Equipment parameters unresolved" in svg
    assert "Sequence-network data incomplete" in svg
    assert "LINE-01†" in svg and "GRID-EQUIVALENT‡" in svg
    assert 'width="180mm"' in svg and 'height="92mm"' in svg
    assert 'data-symbol-id="PFA-SLD-CB-001"' in svg
    assert 'data-symbol-id="PFA-SLD-TRANSFORMER-2W-001"' in svg
    assert 'data-terminal="' in svg
    pdf_path = export_engineering_pdf(document, tmp_path / "single-bus.pdf",
                                      width_mm=180, height_mm=92)
    assert pdf_path.read_bytes().startswith(b"%PDF")


def test_script_api_builds_the_same_switch_and_unresolved_branch_domain_objects():
    result = run_script_worker(
        'project = ScriptProject("Automation canonical model")\n'
        'a = project.add_bus("BUS-A", voltage_kv=13.8)\n'
        'b = project.add_bus("BUS-B", voltage_kv=13.8)\n'
        'project.add_switching_device("CB-API", a, b)\n'
        'project.add_unresolved_branch("LINE-API", a, b, equipment_kind="line", '
        'family=EquipmentFamily.TRANSMISSION, parameters=(("length_km","km"), '
        '("z1","ohm")))\n'
        'workspace = project.render()\n'
    )
    kinds = {item["kind"] for item in result["document"]["network"]["equipment"]}
    assert kinds == {"switching_device", "unresolved_two_terminal_equipment"}
    assert len(result["document"]["network"]["connections"]) == 4
