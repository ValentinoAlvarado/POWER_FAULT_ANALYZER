"""Offscreen acceptance test for the transactional Workbench property editor."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

ROOT = Path(__file__).resolve().parents[1]
for candidate in (str(ROOT), str(ROOT / "src")):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from examples.canonical_model_scenarios import build_single_bus_substation
from power_fault_analyzer.bootstrap.workbench_container import build_workbench_services
from power_fault_analyzer.diagram.model_projection import project_network_to_diagram
from power_fault_analyzer.domain.exceptions.network_exceptions import NetworkDomainError
from power_fault_analyzer.interfaces.desktop.workbench.workbench_window import WorkbenchWindow


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    app = QApplication.instance() or QApplication([])
    window = WorkbenchWindow(build_workbench_services())
    # QWidget.isVisible() includes visibility of every ancestor.  Show the
    # top-level window in the offscreen Qt platform before testing child widgets.
    # Without this, a correctly shown child reports False simply because its
    # QMainWindow ancestor has never been shown by the harness.
    window.show()
    app.processEvents()
    window.workspace = build_single_bus_substation()
    window._bind_workspace_commands()
    bus = window.commands.add_bus("BUS-PROPERTY-TEST", 13.8, 1000.0, 1000.0)
    window.commands.clear_diagram_position(bus.id)
    window._refresh_all()
    app.processEvents()

    # An invalid nominal-voltage edit on a connected bus must be rejected before
    # the QUndoStack changes and without mutating the live aggregate or revision.
    connected_bus = next(
        item for item in window.workspace.network.buses
        if any(connection.bus_id == item.id for connection in window.workspace.network.connections)
    )
    window._inspect_element("bus", str(connected_bus.id))
    invalid_state = dict(window._property_editor_state)
    invalid_state["voltage_kv"] = 66.0
    live_network_before_preflight = window.workspace.network
    live_revision_before_preflight = window.commands.revision
    undo_count_before_preflight = window._undo_stack.count()
    try:
        window._preflight_inspector_state("bus", str(connected_bus.id), invalid_state)
    except NetworkDomainError:
        pass
    else:
        raise AssertionError("Incompatible connected-bus voltage was not rejected by preflight.")
    _require(window.workspace.network is live_network_before_preflight,
             "Rejected preflight replaced the live Network aggregate.")
    _require(window.commands.revision == live_revision_before_preflight,
             "Rejected preflight advanced the live command revision.")
    _require(window._undo_stack.count() == undo_count_before_preflight,
             "Rejected preflight inserted an invalid command into QUndoStack.")
    _require(window.workspace.network.get_bus(connected_bus.id).nominal_voltage.value_kv
             == connected_bus.nominal_voltage.value_kv,
             "Rejected preflight modified the connected bus voltage.")
    print("PASS incompatible bus-voltage edits are rejected before QUndoStack mutation")

    window._inspect_element("bus", str(bus.id))
    network_ref = window.workspace.network
    initial_connections = tuple(window.workspace.network.connections)
    initial_name = bus.name
    initial_voltage = bus.nominal_voltage.value_kv
    initial_position = window._projected_position("bus", bus.id)

    window._inspect_element("bus", str(bus.id))
    app.processEvents()
    _require(window.isVisible(), "Offscreen Workbench top-level window was not shown.")
    _require(window.inspector_tabs.isVisible(), "Workbench inspector tabs are not visible.")
    _require(window.properties_panel.isVisible(), "Properties panel is not visible after selection.")
    _require(window.property_editor_widget.isVisible(), "Bus property editor is not visible.")
    window.property_name_edit.setText("BUS-EDITED")
    window.property_voltage_edit.setValue(33.0)
    window.property_x_edit.setValue(initial_position[0] + 80.0)
    window.property_y_edit.setValue(initial_position[1] + 40.0)
    window.property_rotation_edit.setValue(90.0)
    window._apply_property_editor_changes()
    app.processEvents()

    updated_bus = window.workspace.network.get_bus(bus.id)
    _require(window.workspace.network is network_ref, "Bus edit replaced Network identity.")
    _require(updated_bus.id == bus.id, "Bus edit changed the bus UUID.")
    _require(updated_bus.name == "BUS-EDITED", "Bus name edit was not committed.")
    _require(abs(updated_bus.nominal_voltage.value_kv - 33.0) < 1e-9,
             "Bus voltage edit was not committed.")
    _require(tuple(window.workspace.network.connections) == initial_connections,
             "Bus property edit altered electrical connectivity.")
    _require(window.workspace.diagram_positions[bus.id] == (initial_position[0] + 80.0,
                                                             initial_position[1] + 40.0),
             "Bus position edit was not committed.")
    _require(window.workspace.diagram_rotations[bus.id] == 90.0,
             "Bus rotation edit was not committed.")
    print("PASS bus name, voltage, position and rotation inspector transaction")

    window._undo_stack.undo()
    app.processEvents()
    restored_bus = window.workspace.network.get_bus(bus.id)
    _require(restored_bus.name == initial_name, "Undo did not restore bus name.")
    _require(abs(restored_bus.nominal_voltage.value_kv - initial_voltage) < 1e-9,
             "Undo did not restore nominal voltage.")
    _require(tuple(window.workspace.network.connections) == initial_connections,
             "Undo altered the electrical connections.")
    _require(bus.id not in window.workspace.diagram_positions,
             "Undo did not restore automatic bus positioning metadata.")
    _require(bus.id not in window.workspace.diagram_rotations,
             "Undo did not restore automatic bus orientation metadata.")
    print("PASS property editor undo restores domain state and implicit layout metadata")

    window._undo_stack.redo()
    app.processEvents()
    _require(window.workspace.network.get_bus(bus.id).name == "BUS-EDITED",
             "Redo did not reapply bus name.")
    _require(bus.id in window.workspace.diagram_positions
             and bus.id in window.workspace.diagram_rotations,
             "Redo did not restore explicit layout metadata.")
    print("PASS property editor redo reapplies bus transaction and explicit layout metadata")

    equipment = window.workspace.network.equipment[0]
    document_before = project_network_to_diagram(window.workspace)
    # Generated equipment labels carry a stable semantic UUID. Their visible
    # text may include a status marker (†/‡), so identity must never be inferred
    # by comparing it with the canonical equipment name.
    expected_label_id = uuid5(
        NAMESPACE_URL, f"urn:pfa:diagram-label:{equipment.id}:equipment-name"
    )
    default_label = next(
        (item for item in document_before.labels if item.label_id == expected_label_id),
        None,
    )
    _require(default_label is not None,
             "Canonical equipment display label is missing its stable equipment-name identity.")
    _require(default_label.owner_id == equipment.id,
             "Generated equipment label is not owned by the selected equipment.")
    _require(bool(default_label.text), "Generated equipment display label is empty.")
    window._inspect_element("equipment", str(equipment.id))
    app.processEvents()
    _require(window.property_editor_widget.isVisible(), "Equipment property editor is not visible.")
    window.property_name_edit.setText("GRID-EDITED-DISPLAY")
    window._apply_property_editor_changes()
    app.processEvents()
    document_after = project_network_to_diagram(window.workspace)
    label_after = next(item for item in document_after.labels
                       if item.label_id == default_label.label_id)
    _require(label_after.text == "GRID-EDITED-DISPLAY", "Equipment drawing label was not edited.")
    _require(window.workspace.network.get_equipment(equipment.id).name == equipment.name,
             "Presentation label edit changed canonical equipment identity/name.")
    _require(
        (label_after.position.x, label_after.position.y)
        == (default_label.position.x, default_label.position.y),
        "Renaming a generated EngineeringLabel changed its position unexpectedly.",
    )
    print("PASS generated EngineeringLabel position contract on first label edit")
    label_position_before_move = (label_after.position.x, label_after.position.y)
    equipment_position_before_move = window._projected_position("equipment", equipment.id)
    window._inspect_element("equipment", str(equipment.id))
    window.property_x_edit.setValue(equipment_position_before_move[0] + 45.0)
    window.property_y_edit.setValue(equipment_position_before_move[1] + 25.0)
    window._apply_property_editor_changes()
    app.processEvents()
    moved_label = next(
        item for item in project_network_to_diagram(window.workspace).labels
        if item.label_id == default_label.label_id
    )
    _require(abs(moved_label.position.x - label_position_before_move[0] - 45.0) < 1e-9,
             "Equipment label did not follow the equipment's X displacement.")
    _require(abs(moved_label.position.y - label_position_before_move[1] - 25.0) < 1e-9,
             "Equipment label did not follow the equipment's Y displacement.")
    print("PASS persisted DiagramLabelPlacement x/y contract when equipment moves")
    print("PASS equipment display label follows owner movement without changing electrical identity")

    window._undo_stack.undo()
    app.processEvents()
    restored_label = next(
        item for item in project_network_to_diagram(window.workspace).labels
        if item.label_id == default_label.label_id
    )
    _require((restored_label.position.x, restored_label.position.y) == label_position_before_move,
             "Undo did not restore equipment label position.")
    _require(equipment.id not in window.workspace.diagram_positions,
             "Undo did not restore equipment's automatic layout position.")
    window._undo_stack.undo()
    app.processEvents()
    _require(default_label.label_id not in window.workspace.diagram_labels,
             "Undo did not remove the generated-label override.")
    label_restored = next(item for item in project_network_to_diagram(window.workspace).labels
                          if item.label_id == default_label.label_id)
    _require(label_restored.text == default_label.text,
             "Undo did not restore the exact generated display label, including status markers.")
    window._undo_stack.redo()
    app.processEvents()
    _require(window.workspace.diagram_labels[default_label.label_id].text == "GRID-EDITED-DISPLAY",
             "Redo did not restore custom equipment label.")
    print("PASS equipment label override supports undo and redo")

    # This is an in-memory acceptance harness, not a user project session.
    # Inspector commands mark the window dirty; invoking close() in that state
    # opens the modal Save/Discard/Cancel QMessageBox. Under QT_QPA_PLATFORM=offscreen
    # there is no user to answer it, so the harness appears to hang at teardown.
    # Mark the synthetic workspace clean before closing to exercise closeEvent
    # and canvas shutdown without opening an interactive dialog.
    window._dirty = False
    window.close()
    app.processEvents()
    _require(not window.isVisible(), "Workbench window did not close cleanly after acceptance.")
    print("PASS PFA-WORKBENCH-004.2 offscreen teardown without modal discard prompt")
    print("PASS PFA-WORKBENCH-004.2 interactive property editor acceptance")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
