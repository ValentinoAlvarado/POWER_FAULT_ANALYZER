"""Windows Qt canvas smoke test for PFA-SYNC-001 canonical scenarios."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from examples.canonical_model_scenarios import (
    build_double_bus_substation,
    build_multibus_network,
    build_single_bus_substation,
)
from power_fault_analyzer.interfaces.desktop.workbench.network_canvas import NetworkCanvasView

OUTPUT = ROOT / "outputs" / "pfa_sync_001_qt"
OUTPUT.mkdir(parents=True, exist_ok=True)


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    cases = (
        ("01_single_bus", build_single_bus_substation),
        ("02_double_bus", build_double_bus_substation),
        ("03_multibus", build_multibus_network),
    )
    for name, builder in cases:
        canvas = NetworkCanvasView()
        canvas.resize(1440, 1000)
        canvas.set_workspace(builder())
        canvas.set_grid_visible(False)
        canvas.show()
        app.processEvents()
        bounds = canvas.scene().itemsBoundingRect().adjusted(-80, -80, 80, 80)
        canvas.fitInView(bounds, Qt.AspectRatioMode.KeepAspectRatio)
        app.processEvents()
        target = OUTPUT / f"{name}.png"
        if not canvas.viewport().grab().save(str(target), "PNG"):
            raise RuntimeError(f"Could not save Qt viewport screenshot: {target}")
        print(f"PASS {name}: {target}")
        canvas.close()
    print("PFA-SYNC-001 Qt canvas smoke test passed for all three canonical Network models.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
