from __future__ import annotations

import os
import sys
from uuid import uuid4

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication, QGraphicsScene

from power_fault_analyzer.interfaces.desktop.workbench.network_canvas import (
    CanonicalEquipmentSymbol,
)


def _has_dark_pixel(image: QImage, x: float, y: float, radius: int = 4) -> bool:
    cx, cy = int(round(x)), int(round(y))
    for py in range(max(0, cy - radius), min(image.height(), cy + radius + 1)):
        for px in range(max(0, cx - radius), min(image.width(), cx + radius + 1)):
            color = image.pixelColor(px, py)
            if color.red() < 100 and color.green() < 110 and color.blue() < 130:
                return True
    return False


def main() -> int:
    app = QApplication.instance() or QApplication([])
    scene = QGraphicsScene()
    item = CanonicalEquipmentSymbol(
        uuid4(), "T-QT-TEST", "transformer", None, 68.0, 42.0, 90.0, "T-QT-TEST"
    )
    scene.addItem(item)
    scene.setSceneRect(QRectF(-60.0, -60.0, 120.0, 120.0))

    image = QImage(720, 720, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor("white"))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    scene.render(painter, QRectF(0.0, 0.0, 720.0, 720.0), scene.sceneRect())
    painter.end()
    app.processEvents()

    # Mapping: 120 scene units -> 720 pixels (6 px per scene unit), origin at 360.
    center = 360.0
    scale = 6.0
    intersection_x = 12.49 * scale
    checks = {
        "left circle intersection": (center - intersection_x, center),
        "right circle intersection": (center + intersection_x, center),
        "upper external terminal lead": (center, center - 30.0 * scale),
        "lower external terminal lead": (center, center + 30.0 * scale),
        # A point on the first circle's arc that lies inside the second circle.
        # This must remain ink; an opaque fill on the second circle erases it.
        "visible inner overlap arc": (center - 9.327 * scale, center + 3.0 * scale),
    }
    for name, (x, y) in checks.items():
        if not _has_dark_pixel(image, x, y):
            raise AssertionError(f"Qt transformer glyph is missing {name} at {(x, y)}")

    bounds = item.boundingRect()
    if bounds.top() > -34.0 or bounds.bottom() < 34.0:
        raise AssertionError("Qt transformer bounds clip an external terminal lead.")

    output = os.environ.get("PFA_SYMBOLS_001_QT_PREVIEW")
    if output:
        if not image.save(output, "PNG"):
            raise RuntimeError(f"Unable to save Qt preview to {output}")
        print(f"Qt symbol preview: {output}")

    scene.clear()
    app.processEvents()
    print(
        "PASS PFA-SYMBOLS-001 Qt IEC S00841 Form 1 overlap, transparent winding arcs, "
        "external terminal leads and rotated item bounds."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
