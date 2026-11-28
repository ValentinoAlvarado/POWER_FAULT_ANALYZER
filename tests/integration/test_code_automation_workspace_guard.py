from __future__ import annotations


def test_build_diagram_preserves_dirty_project_when_discard_is_cancelled(qtbot, monkeypatch):
    from power_fault_analyzer.bootstrap.workbench_container import build_workbench_services
    from power_fault_analyzer.interfaces.desktop.workbench.workbench_window import WorkbenchWindow
    from power_fault_analyzer.scripting.project import ScriptProject

    window = WorkbenchWindow(build_workbench_services())
    qtbot.addWidget(window)

    current_project = window.project
    current_workspace = window.workspace
    current_project_path = window.project_path
    scripted_workspace = ScriptProject("Script replacement").workspace
    window._dirty = True
    monkeypatch.setattr(window, "_confirm_discard", lambda: False)

    window._apply_script_workspace(scripted_workspace)

    assert window.project is current_project
    assert window.workspace is current_workspace
    assert window.project_path == current_project_path
    assert window._dirty is True

    window._dirty = False
