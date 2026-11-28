from __future__ import annotations


def test_code_automation_studio_displays_captured_script_output(qtbot) -> None:
    from power_fault_analyzer.interfaces.desktop.workbench.code_automation_studio import (
        CodeAutomationStudio,
    )
    from power_fault_analyzer.scripting.project import ScriptProject

    studio = CodeAutomationStudio()
    qtbot.addWidget(studio)
    project = ScriptProject("Captured output UI test")
    project.add_bus("BUS-01", voltage_kv=13.8)

    studio._mode = "validate"
    studio._worker_succeeded({
        "workspace": project.render(),
        "project_name": project.name,
        "captured_output": "Created BUS-01\nReady for review",
    })

    output = studio.output.toPlainText()
    assert "VALIDATION PASSED" in output
    assert "SCRIPT OUTPUT" in output
    assert "Created BUS-01" in output
    assert "Ready for review" in output
