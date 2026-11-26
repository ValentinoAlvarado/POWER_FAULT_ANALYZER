from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

import pytest

from power_fault_analyzer.application.commands import (
    AddBus,
    MoveDiagramElements,
    NetworkWorkspaceCommands,
    SetDiagramGrid,
    WorkspaceCommandBus,
)
from power_fault_analyzer.application.use_cases.network_workspace import NetworkWorkspace
from power_fault_analyzer.domain.aggregates.network import Network
from power_fault_analyzer.scripting.project import ScriptProject


@dataclass(frozen=True)
class _FailingCommand:
    name: str = "Fail deliberately"

    def execute(self, workspace: NetworkWorkspace) -> None:
        workspace.grid_spacing = 0.0
        raise RuntimeError("forced rollback")


def test_shared_commands_add_and_move_bus_without_touching_topology() -> None:
    workspace = NetworkWorkspace(Network("Command API"))
    commands = NetworkWorkspaceCommands(workspace, source="test")

    bus = commands.add_bus("BUS-A", 13.8, 120.0, 240.0)
    assert workspace.network.get_bus(bus.id) is bus
    assert workspace.diagram_positions[bus.id] == (120.0, 240.0)
    assert workspace.network.connections == ()

    commands.move_elements({bus.id: (180.0, 300.0)})
    assert workspace.diagram_positions[bus.id] == (180.0, 300.0)
    assert workspace.network.connections == ()
    assert commands.revision == 2


def test_command_bus_commits_one_event_and_supports_optimistic_revision() -> None:
    workspace = NetworkWorkspace(Network("Command Events"))
    bus = WorkspaceCommandBus(workspace, source="workbench")
    received = []
    unsubscribe = bus.subscribe(received.append)

    bus.execute_many(
        (
            # Command instances are shared by the Workbench and scripting facade.
            AddBus("BUS-A", 13.8, 50.0, 70.0),
            SetDiagramGrid(24.0, True),
        ),
        expected_revision=0,
    )

    assert bus.revision == 1
    assert len(received) == 1
    assert received[0].source == "workbench"
    assert received[0].revision == 1
    unsubscribe()
    with pytest.raises(RuntimeError, match="Stale workspace revision"):
        bus.execute(
            MoveDiagramElements(((workspace.network.buses[0].id, 80.0, 90.0),)),
            expected_revision=0,
        )


def test_failed_batch_rolls_back_network_and_presentation_atomically() -> None:
    workspace = NetworkWorkspace(Network("Atomic Rollback"))
    original_workspace_id = id(workspace)
    original_network_id = workspace.network.id
    original_network = workspace.network
    bus = WorkspaceCommandBus(workspace, source="test")

    with pytest.raises(KeyError, match="Unknown diagram element"):
        bus.execute_many(
            (
                AddBus("BUS-TEMP", 13.8, 1.0, 2.0),
                MoveDiagramElements(((uuid4(), 3.0, 4.0),)),
            )
        )

    assert id(workspace) == original_workspace_id
    assert workspace.network.id == original_network_id
    assert workspace.network is original_network
    assert workspace.network.buses == ()
    assert workspace.diagram_positions == {}
    assert bus.revision == 0
    assert bus.events == ()


def test_unexpected_command_failure_restores_all_workspace_fields() -> None:
    workspace = NetworkWorkspace(Network("Command Failure"))
    workspace.grid_spacing = 25.0
    bus = WorkspaceCommandBus(workspace)

    with pytest.raises(RuntimeError, match="forced rollback"):
        bus.execute(_FailingCommand())

    assert workspace.grid_spacing == 25.0
    assert bus.revision == 0


def test_script_project_exposes_the_same_transactional_workspace_commands() -> None:
    project = ScriptProject("Automation command bridge")
    assert project.commands.workspace is project.workspace

    bus = project.add_bus("BUS-SCRIPT", 13.8, x=100.0, y=200.0)
    project.move_diagram_element(bus, 160.0, 260.0)
    project.rotate_bus(bus, 90.0)

    assert project.network.get_bus(bus.id).id == bus.id
    assert project.workspace.diagram_positions[bus.id] == (160.0, 260.0)
    assert project.workspace.diagram_rotations[bus.id] == 90.0
    assert project.commands.revision == 3


def test_update_bus_command_preserves_aggregate_and_bus_identity() -> None:
    workspace = NetworkWorkspace(Network("Bus Update"))
    commands = NetworkWorkspaceCommands(workspace)
    bus = commands.add_bus("BUS-OLD", 13.8, 10.0, 20.0)
    network_reference = workspace.network

    updated = commands.update_bus(bus.id, "BUS-NEW", 13.8)

    assert workspace.network is network_reference
    assert updated.id == bus.id
    assert workspace.network.get_bus(bus.id).name == "BUS-NEW"
    assert workspace.diagram_positions[bus.id] == (10.0, 20.0)


def test_script_equipment_and_switch_state_use_transactional_command_facade() -> None:
    from power_fault_analyzer.domain.enums.switching_device import SwitchPosition

    project = ScriptProject("Script command topology")
    bus_a = project.add_bus("BUS-A", 13.8, x=100.0, y=100.0)
    bus_b = project.add_bus("BUS-B", 13.8, x=300.0, y=100.0)
    switch = project.add_switching_device("CB-01", bus_a, bus_b)

    assert len(project.network.connections) == 2
    updated = project.set_switch_position(switch, SwitchPosition.CLOSED)
    assert updated.position is SwitchPosition.CLOSED
    assert len(project.network.connections) == 2
    assert project.commands.revision == 4


def test_script_source_registration_is_atomic_and_uses_explicit_sequence_data() -> None:
    project = ScriptProject("Script source command")
    bus = project.add_bus("BUS-13K8", 13.8)
    source = project.add_equivalent_source(
        "GRID",
        bus,
        base_mva=100.0,
        z1_pu=0.08 + 0.24j,
        z2_pu=0.08 + 0.24j,
        z0_pu=0.08 + 0.24j,
        prefault_voltage_pu=1.0 + 0.0j,
    )

    assert project.network.get_equipment(source.id) is source
    assert len(project.network.connections) == 1
    assert source.terminals[0].id in {item.terminal_id for item in project.network.connections}
    assert project.commands.revision == 2


def test_diagram_label_override_can_be_removed_transactionally() -> None:
    from power_fault_analyzer.application.use_cases.network_workspace import DiagramLabelPlacement

    workspace = NetworkWorkspace(Network("Editable annotation"))
    commands = NetworkWorkspaceCommands(workspace, source="test")
    bus = commands.add_bus("BUS-A", 13.8, 100.0, 120.0)
    label = DiagramLabelPlacement.create(
        "BUS-A custom label", 120.0, 100.0, owner_id=bus.id
    )

    commands.upsert_label(label)
    assert workspace.diagram_labels[label.label_id] == label
    revision_after_insert = commands.revision

    removed = commands.remove_label(label.label_id)

    assert removed == label
    assert label.label_id not in workspace.diagram_labels
    assert commands.revision == revision_after_insert + 1
    assert workspace.network.get_bus(bus.id) is bus
    assert workspace.network.connections == ()


def test_label_override_remove_failure_rolls_back_without_identity_loss() -> None:
    workspace = NetworkWorkspace(Network("Annotation rollback"))
    commands = NetworkWorkspaceCommands(workspace, source="test")
    bus = commands.add_bus("BUS-A", 13.8, 100.0, 120.0)
    network = workspace.network
    revision = commands.revision

    import pytest

    with pytest.raises(KeyError, match="Unknown diagram label"):
        commands.remove_label(uuid4())

    assert workspace.network is network
    assert workspace.network.get_bus(bus.id).id == bus.id
    assert commands.revision == revision


def test_update_bus_preserves_bus_kind_and_terminal_connections() -> None:
    from power_fault_analyzer.domain.enums.bus_kind import BusKind

    workspace = NetworkWorkspace(Network("Bus kind preservation"))
    commands = NetworkWorkspaceCommands(workspace)
    bus = commands.add_bus("NODE-OLD", 13.8, 10.0, 20.0, kind=BusKind.CONNECTION_NODE)

    updated = commands.update_bus(bus.id, "NODE-NEW", 13.8)

    assert updated.id == bus.id
    assert updated.kind is BusKind.CONNECTION_NODE
    assert workspace.network.connections == ()


def test_diagram_label_overrides_round_trip_without_changing_network_topology(tmp_path) -> None:
    from power_fault_analyzer.application.use_cases.network_workspace import DiagramLabelPlacement
    from power_fault_analyzer.infrastructure.persistence.json_network_document_repository import (
        JSONNetworkDocumentRepository,
    )

    workspace = NetworkWorkspace(Network("Inspector persistence"))
    commands = NetworkWorkspaceCommands(workspace)
    bus = commands.add_bus("BUS-A", 13.8, 200.0, 240.0)
    label = DiagramLabelPlacement.create(
        "BUS-A / EDITED", 210.0, 190.0, owner_id=bus.id, size_pt=8.5, weight="semibold"
    )
    commands.upsert_label(label)
    before_connections = tuple(workspace.network.connections)
    repository = JSONNetworkDocumentRepository()

    path = repository.save(workspace, tmp_path / "inspector.pfa.network.json")
    restored = repository.load(path)

    assert restored.network.id == workspace.network.id
    assert restored.network.get_bus(bus.id).name == "BUS-A"
    assert restored.diagram_labels[label.label_id] == label
    assert restored.diagram_positions[bus.id] == (200.0, 240.0)
    assert tuple(restored.network.connections) == before_connections


def test_explicit_diagram_position_and_rotation_can_be_removed_transactionally() -> None:
    workspace = NetworkWorkspace(Network("Restore automatic layout"))
    commands = NetworkWorkspaceCommands(workspace, source="test")
    bus = commands.add_bus("BUS-A", 13.8, 25.0, 40.0)
    commands.rotate_bus(bus.id, 90.0)
    revision = commands.revision

    previous_position = commands.clear_diagram_position(bus.id)
    previous_rotation = commands.clear_diagram_rotation(bus.id)

    assert previous_position == (25.0, 40.0)
    assert previous_rotation == 90.0
    assert bus.id not in workspace.diagram_positions
    assert bus.id not in workspace.diagram_rotations
    assert commands.revision == revision + 2
    assert workspace.network.get_bus(bus.id).id == bus.id


def test_remove_diagram_position_failure_rolls_back_without_revision_change() -> None:
    workspace = NetworkWorkspace(Network("Missing explicit position"))
    commands = NetworkWorkspaceCommands(workspace, source="test")
    bus = commands.add_bus("BUS-A", 13.8, 25.0, 40.0)
    commands.clear_diagram_position(bus.id)
    revision = commands.revision
    network = workspace.network

    with pytest.raises(KeyError, match="No explicit diagram position"):
        commands.clear_diagram_position(bus.id)

    assert workspace.network is network
    assert workspace.network.get_bus(bus.id).id == bus.id
    assert bus.id not in workspace.diagram_positions
    assert commands.revision == revision
