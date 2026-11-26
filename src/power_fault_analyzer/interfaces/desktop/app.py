"""PySide6 desktop application entry point for the engineering workbench."""

from __future__ import annotations

import sys


def main() -> int:
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:
        raise SystemExit(
            "PySide6 is required. Install the desktop dependencies with "
            'python -m pip install -e ".[dev,desktop,reports]".'
        ) from exc

    from power_fault_analyzer.bootstrap.workbench_container import build_workbench_services
    from power_fault_analyzer.interfaces.desktop.workbench.workbench_window import WorkbenchWindow

    application = QApplication(sys.argv)
    application.setApplicationName("POWER_FAULT_ANALYZER")
    application.setOrganizationName("POWER_FAULT_ANALYZER")
    application.setApplicationDisplayName("POWER_FAULT_ANALYZER — Engineering Workbench")
    window = WorkbenchWindow(build_workbench_services())
    # Engineering drawings benefit from the full available viewport by default.
    # The window still remains resizable and persists its splitter layout.
    window.showMaximized()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
