"""PySide6 desktop application entry point for the engineering workbench."""

from __future__ import annotations

import sys


def main() -> int:
    # PyInstaller launches this same executable for the isolated automation
    # worker. Dispatch before importing Qt or constructing QApplication.
    if len(sys.argv) >= 4 and sys.argv[1] == "--pfa-script-worker":
        from power_fault_analyzer.scripting.worker import main as worker_main

        return worker_main(sys.argv[2], sys.argv[3])

    try:
        from PySide6.QtWidgets import QApplication, QStyleFactory
    except ImportError as exc:
        raise SystemExit(
            "PySide6 is required. Install the desktop dependencies with "
            'python -m pip install -e ".[dev,desktop,reports]".'
        ) from exc

    from power_fault_analyzer.bootstrap.workbench_container import build_workbench_services
    from power_fault_analyzer.interfaces.desktop.workbench.workbench_window import WorkbenchWindow

    application = QApplication(sys.argv)
    fusion_style = QStyleFactory.create("Fusion")
    if fusion_style is not None:
        application.setStyle(fusion_style)
    application.setApplicationName("POWER_FAULT_ANALYZER")
    application.setOrganizationName("POWER_FAULT_ANALYZER")
    application.setApplicationDisplayName("POWER_FAULT_ANALYZER — Engineering Workbench")
    window = WorkbenchWindow(build_workbench_services())
    window.showMaximized()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
