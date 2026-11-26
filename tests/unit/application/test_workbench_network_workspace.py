from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest

from power_fault_analyzer.application.use_cases.network_editing import (
    AddBusToNetwork,
    AddLineBetweenBuses,
    LineInput,
)
from power_fault_analyzer.application.use_cases.network_workspace import (
    DiagramSymbolPlacement,
    NetworkStudyRecord,
    NetworkWorkspace,
)
from power_fault_analyzer.application.use_cases.reference_network_template import (
    BuildReferenceNetworkTemplate,
)
from power_fault_analyzer.application.use_cases.run_network_short_circuit_study import (
    RunNetworkShortCircuitStudy,
)
from power_fault_analyzer.domain.aggregates.network import Network
from power_fault_analyzer.domain.enums.fault_type import FaultType
from power_fault_analyzer.infrastructure.adapters.sequence_network_set_factory_adapter import (
    SequenceNetworkSetFactoryAdapter,
)
from power_fault_analyzer.infrastructure.adapters.short_circuit_solver_adapter import (
    NumericalShortCircuitSolverAdapter,
)
from power_fault_analyzer.infrastructure.persistence.json_network_document_repository import (
    JSONNetworkDocumentRepository,
)


def test_reference_template_is_a_physical_network_not_a_drawn_mock() -> None:
    template = BuildReferenceNetworkTemplate().execute("REF-3PH-001")
    network = template.workspace.network

    assert len(network.buses) == 1
    assert network.buses[0].name == "101"
    assert network.buses[0].nominal_voltage.value_kv == pytest.approx(13.8)
    assert len(network.equipment) == 1
    assert type(network.equipment[0]).__name__ == "EquivalentSource"
    assert len(network.connections) == 1
    assert network.connections[0].bus_id == template.fault_bus_id
    assert template.study_settings.base_power_mva == pytest.approx(100.0)
    assert template.study_settings.positive_sequence_impedance_pu == 0.08 + 0.24j
    assert template.study_settings.fault_impedance_pu == 0.025 + 0.07j


def test_network_short_circuit_use_case_reproduces_ref_3ph_001b() -> None:
    template = BuildReferenceNetworkTemplate().execute("REF-3PH-001")
    use_case = RunNetworkShortCircuitStudy(
        NumericalShortCircuitSolverAdapter(), SequenceNetworkSetFactoryAdapter()
    )

    execution = use_case.execute(
        template.workspace.network,
        fault_bus_id=template.fault_bus_id,
        fault_type=FaultType.THREE_PHASE,
        fault_impedance_pu=template.study_settings.fault_impedance_pu,
        base_power_mva=template.study_settings.base_power_mva,
        project_name="REF-3PH-001B Workbench Integration",
    )

    assert abs(abs(execution.result.phase_currents_pu[0]) - 3.117347105392) < 1e-10
    assert abs(abs(execution.result.phase_voltages_pu[0]) - 0.231713481890) < 1e-10
    assert abs(abs(execution.result.phase_currents_ka[0]) - 13.042037611997) < 1e-9
    assert execution.report.metadata.study_name == "Short-circuit at 101"
    assert execution.networks.positive.network_id == template.workspace.network.id
    assert len(execution.networks.positive.nodes) == 1
    assert not execution.diagnostics


def test_network_document_round_trip_preserves_model_and_diagram_layout(tmp_path: Path) -> None:
    template = BuildReferenceNetworkTemplate().execute("REF-3PH-001")
    source = template.workspace.network.equipment[0]
    template.workspace.diagram_positions[source.id] = (40.0, 70.0)
    bus_id = template.workspace.network.buses[0].id
    template.workspace.update_diagram_rotation(bus_id, 90.0)
    execution = RunNetworkShortCircuitStudy(
        NumericalShortCircuitSolverAdapter(), SequenceNetworkSetFactoryAdapter()
    ).execute(
        template.workspace.network,
        fault_bus_id=template.fault_bus_id,
        fault_type=template.study_settings.fault_type,
        fault_impedance_pu=template.study_settings.fault_impedance_pu,
        base_power_mva=template.study_settings.base_power_mva,
        project_name="Persistent history",
    )
    template.workspace.record_study(
        NetworkStudyRecord.create(
            project_name="Persistent history",
            study_name=execution.report.metadata.study_name,
            network_id=template.workspace.network.id,
            fault_bus_id=template.fault_bus_id,
            fault_bus_name="101",
            result=execution.result,
        )
    )
    path = JSONNetworkDocumentRepository().save(template.workspace, tmp_path / "network.pfan")

    loaded = JSONNetworkDocumentRepository().load(path)

    assert loaded.network.id == template.workspace.network.id
    assert len(loaded.network.buses) == 1
    assert len(loaded.network.equipment) == 1
    assert len(loaded.network.connections) == 1
    assert loaded.diagram_positions == template.workspace.diagram_positions
    assert loaded.diagram_rotations == template.workspace.diagram_rotations
    assert len(loaded.study_history) == 1
    assert loaded.study_history[0].result.phase_currents_pu == execution.result.phase_currents_pu
    assert loaded.study_history[0].fault_bus_id == template.fault_bus_id


def test_diagram_symbol_placement_is_independent_and_rotation_is_normalized() -> None:
    placement = DiagramSymbolPlacement.create("IEC-GEN-SYNC-3PH-NEUTRAL", 125.0, 240.0, 450.0)
    workspace = NetworkWorkspace(Network("drawing-only symbol"))
    workspace.add_diagram_symbol(placement)

    assert placement.rotation_deg == pytest.approx(90.0)
    assert not workspace.network.buses
    assert not workspace.network.equipment
    assert not workspace.network.connections
    assert workspace.diagram_symbols[placement.instance_id] == placement

    updated = workspace.update_diagram_symbol(placement.instance_id, x=150.0, rotation_deg=-90.0)
    assert updated.x == pytest.approx(150.0)
    assert updated.rotation_deg == pytest.approx(270.0)
    assert workspace.diagram_symbols[placement.instance_id] == updated


def test_network_document_round_trip_preserves_drawing_symbol_instances(tmp_path: Path) -> None:
    workspace = BuildReferenceNetworkTemplate().execute("REF-3PH-001").workspace
    placement = DiagramSymbolPlacement.create("IEC-GEN-SYNC-3PH-NEUTRAL", 310.0, 180.0, 270.0)
    workspace.add_diagram_symbol(placement)

    path = JSONNetworkDocumentRepository().save(workspace, tmp_path / "diagram-symbol.pfan")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "1.5"
    loaded = JSONNetworkDocumentRepository().load(path)

    assert loaded.diagram_symbols == {placement.instance_id: placement}
    assert loaded.network.id == workspace.network.id
    assert len(loaded.network.equipment) == len(workspace.network.equipment)
    assert loaded.network.equipment[0].id == workspace.network.equipment[0].id


def test_network_document_loads_legacy_1_0_without_symbol_array(tmp_path: Path) -> None:
    workspace = BuildReferenceNetworkTemplate().execute("REF-3PH-001").workspace
    path = JSONNetworkDocumentRepository().save(workspace, tmp_path / "legacy.pfan")
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["schema_version"] = "1.0"
    payload["diagram"].pop("symbols", None)
    path.write_text(json.dumps(payload), encoding="utf-8")

    loaded = JSONNetworkDocumentRepository().load(path)

    assert loaded.diagram_symbols == {}
    assert loaded.network.id == workspace.network.id


def test_network_document_loads_legacy_1_0_symbol_instances_and_rotation(tmp_path: Path) -> None:
    workspace = BuildReferenceNetworkTemplate().execute("REF-3PH-001").workspace
    placement = DiagramSymbolPlacement.create("IEC-GEN-SYNC-3PH-NEUTRAL", 80.0, 120.0, 180.0)
    workspace.add_diagram_symbol(placement)
    path = JSONNetworkDocumentRepository().save(workspace, tmp_path / "legacy-symbols.pfan")
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["schema_version"] = "1.0"
    path.write_text(json.dumps(payload), encoding="utf-8")

    loaded = JSONNetworkDocumentRepository().load(path)

    assert loaded.diagram_symbols == {placement.instance_id: placement}
    assert loaded.diagram_symbols[placement.instance_id].rotation_deg == pytest.approx(180.0)


def test_network_document_loads_legacy_1_0_symbol_without_rotation_as_zero(tmp_path: Path) -> None:
    workspace = BuildReferenceNetworkTemplate().execute("REF-3PH-001").workspace
    placement = DiagramSymbolPlacement.create("IEC-GEN-SYNC-3PH-NEUTRAL", 80.0, 120.0, 0.0)
    workspace.add_diagram_symbol(placement)
    path = JSONNetworkDocumentRepository().save(workspace, tmp_path / "legacy-no-rotation.pfan")
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["schema_version"] = "1.0"
    payload["diagram"]["symbols"][0].pop("rotation_deg", None)
    path.write_text(json.dumps(payload), encoding="utf-8")

    loaded = JSONNetworkDocumentRepository().load(path)

    assert loaded.diagram_symbols[placement.instance_id].rotation_deg == pytest.approx(0.0)


def test_network_document_rejects_unsupported_schema_version(tmp_path: Path) -> None:
    path = tmp_path / "unsupported.pfan"
    path.write_text(json.dumps({"schema_version": "99.0"}), encoding="utf-8")

    with pytest.raises(ValueError, match="supported versions: 1.0, 1.1, 1.2, 1.3, 1.4"):
        JSONNetworkDocumentRepository().load(path)


def test_network_workspace_rejects_layout_positions_for_nonexistent_elements() -> None:
    network = Network("layout validation")

    with pytest.raises(ValueError, match="unknown network element"):
        NetworkWorkspace(network, diagram_positions={uuid4(): (10.0, 20.0)})


def test_line_use_case_rejects_implicit_voltage_level_change_before_mutation() -> None:
    network = Network("two voltage zones")
    add_bus = AddBusToNetwork()
    first = add_bus.execute(network, "HV", 13.8)
    second = add_bus.execute(network, "LV", 4.16)
    specification = LineInput(
        name="Invalid cross-voltage line",
        from_bus_id=first.id,
        to_bus_id=second.id,
        length_km=1.0,
        positive_ohm_per_km=0.1 + 0.2j,
        negative_ohm_per_km=0.1 + 0.2j,
        zero_ohm_per_km=0.3 + 0.8j,
    )

    with pytest.raises(ValueError, match="different nominal voltage levels"):
        AddLineBetweenBuses().execute(network, specification)

    assert not network.equipment
    assert not network.connections


def test_project_workspace_create_preserves_reference_template_settings() -> None:
    from power_fault_analyzer.application.use_cases.project_workspace import (
        ProjectWorkspaceService,
    )

    template = BuildReferenceNetworkTemplate().execute("REF-3PH-001")
    project = ProjectWorkspaceService(repository=None).create(
        "REF-3PH-001B",
        "Physical one-bus Thevenin benchmark network",
        template.study_settings,
    )

    assert project.study_settings == template.study_settings
    assert project.study_settings.positive_sequence_impedance_pu == 0.08 + 0.24j
    assert project.study_settings.fault_impedance_pu == 0.025 + 0.07j


def test_network_workspace_rejects_non_uuid_layout_key() -> None:
    with pytest.raises(TypeError, match="UUID"):
        NetworkWorkspace(Network("invalid layout key"), diagram_positions={"bus-1": (1.0, 2.0)})


def test_network_workspace_normalizes_and_validates_bus_diagram_rotation() -> None:
    workspace = BuildReferenceNetworkTemplate().execute("REF-3PH-001").workspace
    bus_id = workspace.network.buses[0].id

    assert workspace.update_diagram_rotation(bus_id, 450.0) == pytest.approx(90.0)
    assert workspace.diagram_rotations[bus_id] == pytest.approx(90.0)

    with pytest.raises(KeyError, match="Unknown bus"):
        workspace.update_diagram_rotation(uuid4(), 90.0)


def test_network_document_loads_legacy_1_3_without_bus_rotation_map(tmp_path: Path) -> None:
    workspace = BuildReferenceNetworkTemplate().execute("REF-3PH-001").workspace
    path = JSONNetworkDocumentRepository().save(workspace, tmp_path / "legacy-1-3.pfan")
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["schema_version"] = "1.3"
    payload["diagram"].pop("rotations", None)
    path.write_text(json.dumps(payload), encoding="utf-8")

    loaded = JSONNetworkDocumentRepository().load(path)

    assert loaded.diagram_rotations == {}
    assert loaded.network.id == workspace.network.id
