"""Central icon adapter for the desktop workbench.

QtAwesome is the preferred open-source icon pack. Native Qt standard icons remain
available as a fallback for minimal or offline installations.
"""

from __future__ import annotations

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QStyle


def engineering_icon(
    style: QStyle,
    name: str,
    fallback: QStyle.StandardPixmap,
    *,
    color: str = "#334155",
) -> QIcon:
    """Create a themed icon with a deterministic native Qt fallback."""
    try:
        import qtawesome as qta

        icon = qta.icon(name, color=color)
        return icon if not icon.isNull() else style.standardIcon(fallback)
    except (ImportError, KeyError, RuntimeError, ValueError):
        return style.standardIcon(fallback)
