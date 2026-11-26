from pathlib import Path


def test_workbench_keyboard_commands_use_qt_action_ownership_and_canvas_scope():
    root = Path(__file__).resolve().parents[2]
    window = (
        root / "src/power_fault_analyzer/interfaces/desktop/workbench/workbench_window.py"
    ).read_text(encoding="utf-8")
    canvas = (
        root / "src/power_fault_analyzer/interfaces/desktop/workbench/network_canvas.py"
    ).read_text(encoding="utf-8")
    verifier = (root / "scripts/verify_pfa_keyboard_shortcuts.py").read_text(encoding="utf-8")

    for shortcut in (
        'QKeySequence("Ctrl+Z")',
        'QKeySequence("Ctrl+Y")',
        'QKeySequence("Ctrl+Shift+Z")',
        '("Ctrl+A",)',
        '("Escape",)',
        '("Delete", "Backspace")',
        '("Shift+Left",)',
        '("Ctrl+G",)',
    ):
        assert shortcut in window

    # QAction shortcut context is resolved against its QObject parent. Merely
    # calling canvas.addAction(action) does not reparent an existing QAction.
    assert "action.setParent(self.canvas)" in window
    assert "self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)" in canvas
    assert "self.viewport().setFocusPolicy(Qt.FocusPolicy.StrongFocus)" in canvas
    assert "def select_all_elements" in canvas
    assert "def selected_element_refs" in canvas
    assert "def selected_movable_positions" in canvas
    assert "class _DeleteWorkspaceSelectionCommand" in window

    # Regression test must send actual Qt key events, not call the target methods.
    assert "QTest.keyClick(window.canvas.viewport(), Qt.Key.Key_G)" in verifier
    assert "Qt.Key.Key_G, Qt.KeyboardModifier.ControlModifier" in verifier
    assert "Qt.Key.Key_R, Qt.KeyboardModifier.ControlModifier" in verifier
    assert "window._toggle_grid()" not in verifier
    assert "window._toggle_snap()" not in verifier
