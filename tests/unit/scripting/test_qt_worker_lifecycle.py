from __future__ import annotations

_INFINITE_SCRIPT = chr(10).join(("while True:", "    pass", ""))
_MINIMAL_SCRIPT = chr(10).join((
    'project = ScriptProject("Qt worker lifecycle test")',
    'project.add_bus("BUS-01", voltage_kv=13.8)',
    "workspace = project.render()",
    "",
))


def test_qt_worker_timeout_terminates_process_and_releases_resources(qtbot) -> None:
    from power_fault_analyzer.scripting.qt_worker import ScriptWorkerController

    controller = ScriptWorkerController(timeout_ms=150, termination_grace_ms=100)
    failures: list[str] = []
    controller.failed.connect(failures.append)

    controller.start(_INFINITE_SCRIPT)
    qtbot.waitUntil(lambda: bool(failures), timeout=5_000)

    assert "timed out" in failures[0].lower()
    assert controller.process.state() == controller.process.ProcessState.NotRunning
    assert not controller._timeout_timer.isActive()
    assert not controller._termination_timer.isActive()
    assert controller._temporary_directory is None


def test_qt_worker_cancel_stops_termination_timer_before_next_run(qtbot) -> None:
    from power_fault_analyzer.scripting.qt_worker import ScriptWorkerController

    controller = ScriptWorkerController(timeout_ms=5_000, termination_grace_ms=100)
    failures: list[str] = []
    results: list[object] = []
    controller.failed.connect(failures.append)
    controller.succeeded.connect(results.append)

    controller.start(_INFINITE_SCRIPT)
    qtbot.waitUntil(
        lambda: controller.process.state() == controller.process.ProcessState.Running,
        timeout=5_000,
    )
    controller.cancel()
    qtbot.waitUntil(lambda: len(failures) == 1, timeout=5_000)

    assert failures == ["Script execution cancelled."]
    assert not controller._termination_timer.isActive()
    assert not controller._timeout_timer.isActive()
    assert controller._temporary_directory is None

    controller.start(_MINIMAL_SCRIPT)
    qtbot.waitUntil(
        lambda: bool(results) or len(failures) > 1,
        timeout=5_000,
    )

    assert len(failures) == 1, f"Second worker run failed: {failures[1:]}"
    assert len(results) == 1
    assert results[0]["project_name"] == "Qt worker lifecycle test"
    assert controller.process.state() == controller.process.ProcessState.NotRunning
    assert not controller._termination_timer.isActive()
    assert not controller._timeout_timer.isActive()
    assert controller._temporary_directory is None
