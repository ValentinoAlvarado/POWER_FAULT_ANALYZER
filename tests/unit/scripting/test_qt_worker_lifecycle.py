from __future__ import annotations

from power_fault_analyzer.scripting.qt_worker import ScriptWorkerController

from PySide6.QtCore import QProcess


_INFINITE_SCRIPT = "while True:\n    pass\n"
_MINIMAL_SCRIPT = (
    'project = ScriptProject("Qt worker lifecycle test")\n'
    'project.add_bus("BUS-01", voltage_kv=13.8)\n'
    'workspace = project.render()\n'
)


def test_qt_worker_timeout_terminates_process_and_releases_resources(qtbot) -> None:
    controller = ScriptWorkerController(timeout_ms=150, termination_grace_ms=100)
    failures: list[str] = []
    controller.failed.connect(failures.append)

    controller.start(_INFINITE_SCRIPT)
    qtbot.waitUntil(lambda: bool(failures), timeout=5_000)

    assert "timed out" in failures[0].lower()
    assert controller.process.state() == QProcess.ProcessState.NotRunning
    assert not controller._timeout_timer.isActive()
    assert not controller._termination_timer.isActive()
    assert controller._temporary_directory is None


def test_qt_worker_cancel_stops_termination_timer_before_next_run(qtbot) -> None:
    controller = ScriptWorkerController(timeout_ms=5_000, termination_grace_ms=100)
    failures: list[str] = []
    results: list[object] = []
    controller.failed.connect(failures.append)
    controller.succeeded.connect(results.append)

    controller.start(_INFINITE_SCRIPT)
    qtbot.waitUntil(
        lambda: controller.process.state() == QProcess.ProcessState.Running,
        timeout=5_000,
    )
    controller.cancel()
    qtbot.waitUntil(lambda: len(failures) == 1, timeout=5_000)

    assert "cancelled" in failures[0].lower()
    assert not controller._termination_timer.isActive()
    assert controller._temporary_directory is None

    controller.start(_MINIMAL_SCRIPT)
    qtbot.waitUntil(lambda: len(results) == 1, timeout=5_000)

    assert results[0]["project_name"] == "Qt worker lifecycle test"
    assert controller.process.state() == QProcess.ProcessState.NotRunning
    assert not controller._termination_timer.isActive()
