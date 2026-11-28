"""Windows/offscreen acceptance test for PFA Workbench keyboard shortcuts."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for candidate in (str(ROOT), str(ROOT / "src")):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from power_fault_analyzer.bootstrap.workbench_container import build_workbench_services
from power_fault_analyzer.interfaces.desktop.workbench.workbench_window import WorkbenchWindow


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def shortcut_strings(action) -> set[str]:
    return {
        sequence.toString(QKeySequence.SequenceFormat.PortableText)
        for sequence in action.shortcuts()
    }


def main() -> int:
    app = QApplication.instance() or QApplication([])
    window = WorkbenchWindow(build_workbench_services())
    window.show()
    app.processEvents()

    require("Ctrl+Z" in shortcut_strings(window.undo_action), "Undo is not bound to Ctrl+Z.")
    redo = shortcut_strings(window.redo_action)
    require({"Ctrl+Y", "Ctrl+Shift+Z"}.issubset(redo), "Redo must support Ctrl+Y and Ctrl+Shift+Z.")
    require(window.undo_action.shortcutContext() == Qt.ShortcutContext.WidgetWithChildrenShortcut,
            "Undo must be scoped to the diagram canvas.")
    require(window.redo_action.shortcutContext() == Qt.ShortcutContext.WidgetWithChildrenShortcut,
            "Redo must be scoped to the diagram canvas.")
    require(window.undo_action.parent() is window.canvas,
            "Undo QAction must be owned by the canvas shortcut scope.")
    require(window.redo_action.parent() is window.canvas,
            "Redo QAction must be owned by the canvas shortcut scope.")
    require(window.canvas.focusPolicy() == Qt.FocusPolicy.StrongFocus,
            "Canvas must accept keyboard focus.")
    require(window.canvas.viewport().focusPolicy() == Qt.FocusPolicy.StrongFocus,
            "Canvas viewport must accept keyboard focus.")
    for action in (
        window.remove_selected_action,
        window.rotate_clockwise_action,
        window.rotate_counterclockwise_action,
        window.fit_diagram_action,
        window.grid_action,
        window.snap_action,
    ):
        require(action.parent() is window.canvas,
                f"Canvas shortcut action {action.text()!r} has the wrong QObject parent.")
        require(action.shortcutContext() == Qt.ShortcutContext.WidgetWithChildrenShortcut,
                f"Canvas shortcut action {action.text()!r} has the wrong shortcut context.")
    require(window.save_action.parent() is window,
            "File actions must remain owned by the main window.")
    require("Ctrl+S" in shortcut_strings(window.save_action), "Save shortcut is missing.")
    require("Ctrl+O" in shortcut_strings(window.open_action), "Open shortcut is missing.")
    require("Ctrl+N" in shortcut_strings(window.new_action), "New shortcut is missing.")
    print("PASS QAction parent ownership, shortcut contexts, focus policy and file bindings")

    bus_a = window.commands.add_bus("SHORTCUT-BUS-A", 13.8, 200.0, 200.0)
    bus_b = window.commands.add_bus("SHORTCUT-BUS-B", 13.8, 420.0, 200.0)
    window._refresh_all()
    app.processEvents()

    window.canvas.select_element(bus_a.id)
    app.processEvents()
    before = window.canvas.selected_movable_positions()
    require(len(before) == 1, "Selected bus was not exposed as one movable diagram element.")
    old_x, old_y = before[0][1], before[0][2]
    window.canvas.setFocus()
    QTest.keyClick(window.canvas.viewport(), Qt.Key.Key_Right)
    app.processEvents()
    after = window.canvas.selected_movable_positions()
    require(len(after) == 1 and after[0][1] != old_x,
            "Right-arrow nudge did not move the selected bus.")
    new_x, new_y = after[0][1], after[0][2]
    QTest.keyClick(window.canvas.viewport(), Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    app.processEvents()
    restored = window.canvas.selected_movable_positions()
    require(restored and abs(restored[0][1] - old_x) < 1e-9 and abs(restored[0][2] - old_y) < 1e-9,
            "Ctrl+Z did not undo the nudge.")
    QTest.keyClick(window.canvas.viewport(), Qt.Key.Key_Y, Qt.KeyboardModifier.ControlModifier)
    app.processEvents()
    redone = window.canvas.selected_movable_positions()
    require(redone and abs(redone[0][1] - new_x) < 1e-9 and abs(redone[0][2] - new_y) < 1e-9,
            "Ctrl+Y/Ctrl+Shift+Z did not redo the nudge.")
    QTest.keyClick(window.canvas.viewport(), Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    app.processEvents()
    QTest.keyClick(
        window.canvas.viewport(), Qt.Key.Key_Z,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
    )
    app.processEvents()
    redone_alt = window.canvas.selected_movable_positions()
    require(redone_alt and abs(redone_alt[0][1] - new_x) < 1e-9,
            "Ctrl+Shift+Z did not redo the nudge.")
    print("PASS arrow nudge is one undoable/redoable diagram command")

    # A property QLineEdit must retain its local Ctrl+Z behavior; canvas shortcuts
    # must not steal standard editing commands from text-entry controls.
    window.canvas.select_element(bus_a.id)
    app.processEvents()
    window._focus_property_editor()
    editor = window.property_name_edit
    before_text = editor.text()
    stack_index = window._undo_stack.index()
    editor.selectAll()
    QTest.keyClicks(editor, "KEYBOARD-TEXT")
    QTest.keyClick(editor, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    app.processEvents()
    require(editor.text() == before_text, "Ctrl+Z was intercepted from the property text field.")
    require(window._undo_stack.index() == stack_index,
            "Text-field Ctrl+Z incorrectly changed the diagram undo stack.")
    grid_while_editing = window.canvas.grid_visible
    QTest.keyClick(editor, Qt.Key.Key_G)
    app.processEvents()
    require(window.canvas.grid_visible is grid_while_editing,
            "Canvas G shortcut leaked into the property editor.")
    print("PASS canvas shortcuts do not intercept property text editing")

    window.canvas.setFocus()
    QTest.keyClick(window.canvas.viewport(), Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    app.processEvents()
    require(len(window.canvas.selected_element_refs()) == 2,
            "Ctrl+A selection did not select both visible buses.")
    QTest.keyClick(window.canvas.viewport(), Qt.Key.Key_Escape)
    app.processEvents()
    require(not window.canvas.selected_element_refs(), "Escape did not clear canvas selection.")
    print("PASS select-all and Escape clear-selection behavior")

    window.canvas.setFocus()
    grid_before = window.canvas.grid_visible
    QTest.keyClick(window.canvas.viewport(), Qt.Key.Key_G)
    app.processEvents()
    require(window.canvas.grid_visible is not grid_before,
            "G key event did not toggle grid visibility.")
    snap_before = window.workspace.snap_enabled
    QTest.keyClick(window.canvas.viewport(), Qt.Key.Key_G, Qt.KeyboardModifier.ControlModifier)
    app.processEvents()
    require(window.workspace.snap_enabled is not snap_before,
            "Ctrl+G key event did not toggle snap state.")
    print("PASS actual G and Ctrl+G key events toggle grid and snap")

    # Rotation must be a real key event and an undoable workspace operation.
    window.canvas.select_element(bus_a.id)
    window.canvas.setFocus()
    rotation_before = window.workspace.diagram_rotations.get(bus_a.id, 0.0)
    QTest.keyClick(window.canvas.viewport(), Qt.Key.Key_R, Qt.KeyboardModifier.ControlModifier)
    app.processEvents()
    rotation_after = window.workspace.diagram_rotations.get(bus_a.id, 0.0)
    require(rotation_after == (rotation_before + 90.0) % 360.0,
            "Ctrl+R did not rotate the selected busbar.")
    QTest.keyClick(window.canvas.viewport(), Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    app.processEvents()
    require(window.workspace.diagram_rotations.get(bus_a.id, 0.0) == rotation_before,
            "Ctrl+Z did not undo busbar rotation.")
    QTest.keyClick(
        window.canvas.viewport(), Qt.Key.Key_R,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
    )
    app.processEvents()
    require(window.workspace.diagram_rotations.get(bus_a.id, 0.0) ==
            (rotation_before - 90.0) % 360.0,
            "Ctrl+Shift+R did not rotate the selected busbar counterclockwise.")
    print("PASS actual clockwise/counterclockwise rotation and undo key events")

    # Delete is a transactional command and can be restored with Ctrl+Z.
    window.canvas.select_element(bus_b.id)
    app.processEvents()
    window.canvas.setFocus()
    QTest.keyClick(window.canvas.viewport(), Qt.Key.Key_Delete)
    app.processEvents()
    require(all(bus.id != bus_b.id for bus in window.workspace.network.buses),
            "Delete did not remove the selected bus.")
    QTest.keyClick(window.canvas.viewport(), Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    app.processEvents()
    require(any(bus.id == bus_b.id for bus in window.workspace.network.buses),
            "Ctrl+Z did not restore the deleted bus with its original identity.")
    QTest.keyClick(window.canvas.viewport(), Qt.Key.Key_Y, Qt.KeyboardModifier.ControlModifier)
    app.processEvents()
    require(all(bus.id != bus_b.id for bus in window.workspace.network.buses),
            "Redo did not reapply bus deletion.")
    QTest.keyClick(window.canvas.viewport(), Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    app.processEvents()
    print("PASS Delete selection is atomic and undoable with stable bus identity")

    transform_before = window.canvas.transform().m11()
    window.canvas.setFocus()
    QTest.keyClick(window.canvas.viewport(), Qt.Key.Key_Plus, Qt.KeyboardModifier.ControlModifier)
    require(window.canvas.transform().m11() > transform_before,
            "Ctrl+Plus zoom action did not increase scale.")
    window._zoom_diagram(1.0 / 1.2)
    print("PASS zoom keyboard command targets")

    window._dirty = False
    window.close()
    app.processEvents()
    require(not window.isVisible(), "Workbench did not close after keyboard acceptance.")
    print("PASS PFA-KEYBOARD-001 keyboard shortcuts acceptance")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
