"""Windows/offscreen integration smoke test for the PFA-ES-001 desktop workflow."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication

from power_fault_analyzer.bootstrap.workbench_container import build_workbench_services
from power_fault_analyzer.equipment.interfaces.unresolved_equipment import (
    UnresolvedEquipmentInterface,
)
from power_fault_analyzer.equipment.switching.switching_device import SwitchingDevice
from power_fault_analyzer.interfaces.desktop.workbench.workbench_window import WorkbenchWindow


def main() -> int:
    application = QApplication.instance() or QApplication([])
    services = build_workbench_services()
    window = WorkbenchWindow(services)
    qt_exceptions: list[str] = []
    original_excepthook = sys.excepthook

    def record_qt_exception(exception_type, exception_value, traceback) -> None:
        qt_exceptions.append(f"{exception_type.__name__}: {exception_value}")
        original_excepthook(exception_type, exception_value, traceback)

    sys.excepthook = record_qt_exception
    try:
        window.pfa_es001_button.click()
        application.processEvents()

        network = window.workspace.network
        assert window.project.name == "PFA-ES-001"
        assert len(network.buses) == 8
        assert len(network.equipment) == 10
        assert sum(isinstance(item, SwitchingDevice) for item in network.equipment) == 8
        assert (
            sum(isinstance(item, UnresolvedEquipmentInterface) for item in network.equipment) == 2
        )
        assert len(window.workspace.diagram_symbols) == 10
        assert len(window.canvas.source_candidate_items()) == 10, (
            "The pinned source library did not render all mapped candidate symbols."
        )

        # The rotation toolbar must support the selected busbar, not only QET drawing items.
        first_bus = network.buses[0]
        window.canvas.select_element(first_bus.id)
        window.rotate_cw_toolbar_action.trigger()
        application.processEvents()
        assert window.workspace.diagram_rotations[first_bus.id] == 90.0
        assert window.canvas._bus_items[str(first_bus.id)].rotation() == 90.0

        with tempfile.TemporaryDirectory(prefix="pfa-es001-smoke-") as directory:
            target = Path(directory) / "pfa-es-001.network.json"
            services.network_document_repository.save(window.workspace, target)
            restored = services.network_document_repository.load(target)
            assert len(restored.network.equipment) == 10
            assert len(restored.diagram_symbols) == 10
            assert len(restored.network.connections) == 18
    finally:
        try:
            # The smoke creates an intentionally unsaved in-memory project.
            # Force deferred QObject deletion while the exception hook remains
            # installed so teardown-time Qt slot failures fail this test.
            window._dirty = False
            window.close()
            window.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            application.processEvents()
        finally:
            sys.excepthook = original_excepthook

    if qt_exceptions:
        raise RuntimeError(
            "Qt callback exception(s) during desktop smoke teardown: " + "; ".join(qt_exceptions)
        )

    print("PFA-ES-001 DESKTOP SMOKE: PASS")
    print("Project -> equipment -> terminals -> topology -> QET mapping -> JSON rehydration")
    print("Calculation status: BLOCKED until line and transformer input data are verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
