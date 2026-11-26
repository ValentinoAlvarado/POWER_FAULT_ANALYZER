"""Runtime smoke test for the shared PFA transactional workspace command API."""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from power_fault_analyzer.application.commands import (
    AddBus,
    MoveDiagramElements,
    NetworkWorkspaceCommands,
    SetDiagramGrid,
)
from power_fault_analyzer.application.use_cases.network_workspace import (
    DiagramLabelPlacement,
    NetworkWorkspace,
)
from power_fault_analyzer.domain.aggregates.network import Network
from power_fault_analyzer.domain.enums.switching_device import SwitchPosition
from power_fault_analyzer.scripting.project import ScriptProject


def main() -> int:
    workspace = NetworkWorkspace(Network("PFA-WORKBENCH-004.1 smoke"))
    commands = NetworkWorkspaceCommands(workspace, source="verification")
    events = []
    commands.subscribe(events.append)

    bus_a = commands.add_bus("BUS-A", 13.8, 120.0, 140.0)
    bus_b = commands.add_bus("BUS-B", 13.8, 360.0, 140.0)
    commands.move_elements({bus_a.id: (160.0, 180.0), bus_b.id: (400.0, 180.0)})
    commands.rotate_bus(bus_a.id, 90.0)
    commands.set_grid(20.0, True)
    label = DiagramLabelPlacement.create("BUS-A annotation", 160.0, 150.0, owner_id=bus_a.id)
    commands.upsert_label(label)

    if workspace.diagram_positions[bus_a.id] != (160.0, 180.0):
        raise RuntimeError("Diagram move command did not commit.")
    if workspace.diagram_rotations[bus_a.id] != 90.0:
        raise RuntimeError("Bus rotation command did not commit.")
    if workspace.diagram_labels[label.label_id] != label:
        raise RuntimeError("Diagram annotation command did not commit.")
    if len(events) != 6 or commands.revision != 6:
        raise RuntimeError("Command revision/event journal is inconsistent.")

    network_reference = workspace.network
    before_count = len(workspace.network.buses)
    try:
        commands.execute_many(
            (
                AddBus("BUS-ROLLBACK", 13.8, 1.0, 1.0),
                MoveDiagramElements(((uuid4(), 5.0, 5.0),)),
            )
        )
    except KeyError:
        pass
    else:
        raise RuntimeError("Invalid command batch unexpectedly committed.")
    if workspace.network is not network_reference or len(workspace.network.buses) != before_count:
        raise RuntimeError("Failed transaction did not restore the original aggregate.")
    if commands.revision != 6 or len(events) != 6:
        raise RuntimeError("Failed transaction published a revision or command event.")

    script = ScriptProject("PFA-WORKBENCH-004.1 automation smoke")
    script_bus_a = script.add_bus("SCRIPT-BUS-A", 13.8)
    script_bus_b = script.add_bus("SCRIPT-BUS-B", 13.8, x=300.0, y=260.0)
    switch = script.add_switching_device("SCRIPT-CB-01", script_bus_a, script_bus_b)
    script.set_switch_position(switch, SwitchPosition.CLOSED)
    script.move_diagram_element(script_bus_a, 200.0, 220.0)
    if script.commands.workspace is not script.workspace:
        raise RuntimeError("Code & Automation is not bound to the canonical workspace.")
    if script.network.get_equipment(switch.id).position is not SwitchPosition.CLOSED:
        raise RuntimeError("Script switch-position command did not commit.")
    if len(script.network.connections) != 2:
        raise RuntimeError("Script command API altered terminal connection cardinality.")

    print("PASS transactional command commit, revision and event publication")
    print("PASS atomic rollback preserves NetworkWorkspace and Network identities")
    print("PASS Workbench command API: buses, moves, rotations, labels and grid")
    print("PASS Code & Automation shares the same NetworkWorkspace command facade")
    print("PASS switch state update preserves terminal identities and connections")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
