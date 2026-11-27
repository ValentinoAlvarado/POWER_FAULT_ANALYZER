"""Qt Graphics View canvas: rendering metadata is deliberately separate from topology."""

from __future__ import annotations

import math
from functools import lru_cache
from uuid import UUID

from PySide6.QtCore import QObject, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontDatabase,
    QFontMetricsF,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsObject,
    QGraphicsPathItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsTextItem,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QVBoxLayout,
)

from power_fault_analyzer.application.use_cases.network_workspace import (
    DiagramLabelPlacement,
    DiagramSymbolPlacement,
    NetworkWorkspace,
)
from power_fault_analyzer.diagram.layout import (
    Point,
    perpendicular_bay_route,
    select_straight_bus_taps,
    snap_point,
)
from power_fault_analyzer.diagram.model_projection import (
    LABEL_SCENE_UNITS_PER_PT,
    DiagramProjectionError,
    EngineeringLabel,
    project_network_to_diagram,
)
from power_fault_analyzer.diagram.symbol_catalog import get_symbol_definition
from power_fault_analyzer.domain.enums.bus_kind import BusKind
from power_fault_analyzer.equipment.sources.equivalent_source import EquivalentSource
from power_fault_analyzer.equipment.sources.synchronous_generator import SynchronousGenerator
from power_fault_analyzer.infrastructure.symbols.qet_elmt import SymbolDefinition
from power_fault_analyzer.interfaces.desktop.workbench.qet_symbol_item import QETSymbolItem
from power_fault_analyzer.operations import analyze_workspace
from power_fault_analyzer.operations.models import BusOperatingState

ROLE_ELEMENT = 0

# Keep the preferred face first, but never ask Qt to draw with a family that is
# not installed. Qt may otherwise return a missing-glyph box for every Latin
# character in offscreen rendering environments.
_SCENE_FONT_FALLBACKS = (
    "Segoe UI",
    "Arial",
    "Aptos",
    "Calibri",
    "Tahoma",
    "Liberation Sans",
    "DejaVu Sans",
    "Noto Sans",
)


@lru_cache(maxsize=1)
def _installed_scene_font_families() -> tuple[str, ...]:
    """Cache the system font inventory; it does not change during a session."""
    return tuple(QFontDatabase.families())


def _resolve_scene_font_family(
    family: str,
    available_families: tuple[str, ...] | list[str] | None = None,
) -> str:
    """Resolve a requested font to an installed face with Latin glyph coverage.

    ``available_families`` is injectable for deterministic unit tests. The
    production path queries the current Qt font database at runtime.
    """
    families = (
        _installed_scene_font_families()
        if available_families is None
        else tuple(available_families)
    )
    by_name = {
        name.partition(" [")[0].casefold(): name
        for name in families
        if isinstance(name, str) and name.strip()
    }
    requested = family.strip() if isinstance(family, str) else ""
    for candidate in (requested, *_SCENE_FONT_FALLBACKS):
        resolved = by_name.get(candidate.casefold())
        if resolved is not None:
            return resolved

    system_family = QFontDatabase.systemFont(
        QFontDatabase.SystemFont.GeneralFont
    ).family()
    return by_name.get(system_family.casefold(), system_family or "Sans Serif")


@lru_cache(maxsize=1)
def _available_label_font_families() -> tuple[str, ...]:
    """Return a short, useful font menu containing only installed families."""
    families = _installed_scene_font_families()
    by_name = {
        name.partition(" [")[0].casefold(): name
        for name in families
        if isinstance(name, str) and name.strip()
    }
    preferred = (
        "Segoe UI",
        "Arial",
        "Aptos",
        "Calibri",
        "Cambria",
        "Times New Roman",
        "STIX Two Text",
        "Tahoma",
        "Liberation Sans",
        "DejaVu Sans",
        "Noto Sans",
    )
    options = tuple(
        by_name[name.casefold()]
        for name in preferred
        if name.casefold() in by_name
    )
    if options:
        return options
    return (_resolve_scene_font_family(""),)


def _scene_font(
    family: str,
    size_pt: float,
    weight: QFont.Weight = QFont.Weight.Normal,
) -> QFont:
    """Create a scene-scaled font using a verified installed font family.

    EngineeringLabel sizes are physical points in the document model. The
    drawing scene uses approximately 2.8 scene units per typographic point;
    pixel-sized fonts keep the scene geometry deterministic. Resolving the
    family first prevents the missing-glyph squares seen when STIX Two Text is
    requested on a machine where that family is not installed.
    """
    resolved_family = _resolve_scene_font_family(family)
    font = QFont(resolved_family)
    font.setStyleHint(QFont.StyleHint.SansSerif)
    font.setPixelSize(max(1, round(float(size_pt) * LABEL_SCENE_UNITS_PER_PT)))
    font.setWeight(weight)
    return font


def _snap_graphics_position(position: QPointF, enabled: bool, spacing: float) -> QPointF:
    """Apply the workspace's single scene-grid contract to a movable symbol."""
    if not enabled:
        return position
    snapped = snap_point(Point(float(position.x()), float(position.y())), float(spacing))
    return QPointF(snapped.x, snapped.y)


class BusSymbol(QGraphicsObject):
    moved = Signal(str, float, float)
    move_committed = Signal(str, float, float, float, float)

    def __init__(
        self, identifier: UUID, name: str, nominal_kv: float, snap: bool, kind: BusKind,
        width: float = 600.0, operating_state: BusOperatingState | None = None,
        grounded: bool = False, grid_spacing: float = 20.0,
    ) -> None:
        super().__init__()
        self._initializing = True
        self.identifier = identifier
        self.name = name
        self.nominal_kv = nominal_kv
        self.snap = bool(snap)
        self.grid_spacing = float(grid_spacing)
        self.kind = kind
        self.width = float(width)
        self.operating_state = operating_state
        self.operating_grounded = bool(grounded)
        self._drag_start = QPointF()
        self._dragging = False
        self.setData(ROLE_ELEMENT, ("bus", str(identifier)))
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setZValue(20)
        self._initializing = False

    def boundingRect(self) -> QRectF:
        if self.kind is BusKind.BUSBAR:
            return QRectF(-self.width / 2.0 - 6.0, -8.0, self.width + 12.0, 16.0)
        return QRectF(-10.0, -10.0, 20.0, 20.0)

    def connection_point(self, target: QPointF, axis_offset: float | None = None) -> QPointF:
        """Return the terminal's reserved bay tap, or its nearest point if unset."""
        if self.kind is BusKind.BUSBAR:
            angle = math.radians(self.rotation())
            axis = QPointF(math.cos(angle), math.sin(angle))
            if axis_offset is None:
                delta = target - self.pos()
                projection = delta.x() * axis.x() + delta.y() * axis.y()
            else:
                projection = float(axis_offset)
            projection = max(-self.width / 2.0, min(self.width / 2.0, projection))
            return self.pos() + axis * projection
        return self.pos()

    def paint(self, painter: QPainter, option, widget=None) -> None:
        del option, widget
        selected = self.isSelected()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if selected:
            ink = QColor("#B66B12")
        elif self.operating_grounded:
            ink = QColor("#B91C1C")
        elif self.operating_state is BusOperatingState.ENERGIZED:
            ink = QColor("#15803D")
        elif self.operating_state is BusOperatingState.DEENERGIZED:
            ink = QColor("#94A3B8")
        else:
            ink = QColor("#172033")
        if self.kind is BusKind.BUSBAR:
            painter.setPen(QPen(ink, 2.0 * LABEL_SCENE_UNITS_PER_PT,
                                Qt.PenStyle.SolidLine, Qt.PenCapStyle.SquareCap))
            painter.drawLine(QPointF(-self.width / 2.0, 0.0), QPointF(self.width / 2.0, 0.0))
        else:
            painter.setPen(QPen(ink, 0.7 * LABEL_SCENE_UNITS_PER_PT))
            painter.setBrush(QBrush(QColor("#FFFFFF")))
            painter.drawEllipse(QRectF(-4.0, -4.0, 8.0, 8.0))

    def mousePressEvent(self, event) -> None:
        self._drag_start = self.pos()
        self._dragging = True
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        try:
            super().mouseReleaseEvent(event)
            current = self.pos()
            if (current - self._drag_start).manhattanLength() > 0.1:
                self.move_committed.emit(
                    str(self.identifier),
                    self._drag_start.x(),
                    self._drag_start.y(),
                    current.x(),
                    current.y(),
                )
        finally:
            self._dragging = False

    def itemChange(self, change, value):
        if (change is QGraphicsItem.GraphicsItemChange.ItemPositionChange
                and self._dragging and self.snap):
            return _snap_graphics_position(value, True, self.grid_spacing)
        if (
            change is QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged
            and not getattr(self, "_initializing", True)
        ):
            point = self.pos()
            self.moved.emit(
                str(self.identifier), point.x(), point.y()
            )
        return super().itemChange(change, value)


class CanonicalEquipmentSymbol(QGraphicsObject):
    """Selectable Qt symbol projected from a canonical equipment identity."""

    moved = Signal(str, float, float)
    move_committed = Signal(str, float, float, float, float)
    label_changed = Signal(str, str)

    def __init__(self, identifier: UUID, name: str, family: str, state: str | None,
                 width: float, height: float, orientation_deg: float = 0.0,
                 label_text: str | None = None, operating_override: bool = False,
                 snap_enabled: bool = True, grid_spacing: float = 20.0) -> None:
        super().__init__()
        self._initializing = True
        self.identifier, self.name, self.family, self.state = identifier, name, family, state
        self.width, self.height = width, height
        self.orientation_deg = orientation_deg
        self.operating_override = bool(operating_override)
        self.snap_enabled = bool(snap_enabled)
        self.grid_spacing = float(grid_spacing)
        self._drag_start = QPointF()
        self._dragging = False
        self.setData(ROLE_ELEMENT, ("equipment", str(identifier)))
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsMovable
                      | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
                      | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setZValue(18)
        # Text is a separate movable DiagramLabelItem; this item owns only glyph geometry.
        self.label_text = label_text or name
        self._initializing = False

    def boundingRect(self) -> QRectF:
        # Account for the rotated local glyph so winding arcs and terminal leads
        # remain inside the QGraphicsItem scene bounds.
        angle = math.radians(self.orientation_deg)
        # Some switching marks extend beyond the nominal equipment envelope.
        # Include their full scene-space geometry so QGraphicsView does not clip
        # them and itemsBoundingRect()/fitInView sees the real visual extent.
        switch_extension = {
            "circuit_breaker": 3.2 * LABEL_SCENE_UNITS_PER_PT,
            "disconnector": 4.5 * LABEL_SCENE_UNITS_PER_PT,
            "earthing_switch": 11.0 * LABEL_SCENE_UNITS_PER_PT,
        }.get(self.family, 8.0)
        status_extension = 24.0 if self.state in {"unresolved", "partial-data"} else 8.0
        local_half_width = self.width / 2.0 + max(8.0, switch_extension, status_extension)
        local_half_height = self.height / 2.0 + max(8.0, status_extension)
        half_width = (
            abs(math.cos(angle)) * local_half_width
            + abs(math.sin(angle)) * local_half_height
        )
        half_height = (
            abs(math.sin(angle)) * local_half_width
            + abs(math.cos(angle)) * local_half_height
        )
        return QRectF(-half_width, -half_height, 2.0 * half_width, 2.0 * half_height)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        del option, widget
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        selected = self.isSelected()
        ink = QColor("#D97706" if selected else "#2563EB" if self.operating_override else "#172033")
        scene_scale = LABEL_SCENE_UNITS_PER_PT
        painter.save()
        painter.rotate(self.orientation_deg)
        painter.setPen(QPen(ink, 0.7 * scene_scale))
        painter.setBrush(QBrush(QColor("#FFFFFF")))
        if self.family == "transformer":
            # Renderer-neutral parametric primitives are shared with SVG/PDF.
            # No fill is used, so both intersecting winding circumferences remain visible.
            painter.setBrush(Qt.BrushStyle.NoBrush)
            definition = get_symbol_definition("transformer")
            for primitive in definition.primitives:
                if primitive.kind == "circle":
                    px, py, radius = primitive.coordinates
                    painter.drawEllipse(QPointF(px, py), radius, radius)
                elif primitive.kind == "line":
                    x1, y1, x2, y2 = primitive.coordinates
                    painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))
        elif self.family in {"circuit_breaker", "disconnector", "earthing_switch"}:
            left, right = -self.width / 2.0, self.width / 2.0
            contact_radius = 2.0 * scene_scale
            painter.setBrush(QBrush(ink))
            painter.drawEllipse(QPointF(left, 0), contact_radius, contact_radius)
            painter.drawEllipse(QPointF(right, 0), contact_radius, contact_radius)
            painter.setBrush(Qt.BrushStyle.NoBrush)

            if self.family == "circuit_breaker":
                if self.state == "closed":
                    painter.setPen(QPen(ink, 1.55 * scene_scale))
                    painter.drawLine(QPointF(left, 0), QPointF(right, 0))
                else:
                    painter.setPen(QPen(ink, 1.15 * scene_scale))
                    painter.drawLine(QPointF(left, 0), QPointF(2.0, -self.height * 0.32))
                # IEC candidate mark; normative status remains NOT_VERIFIED.
                painter.setPen(QPen(ink, 0.7 * scene_scale))
                mark_y = -self.height * 0.43
                radius = 3.2 * scene_scale
                painter.drawLine(QPointF(right - radius, mark_y - radius),
                                 QPointF(right + radius, mark_y + radius))
                painter.drawLine(QPointF(right - radius, mark_y + radius),
                                 QPointF(right + radius, mark_y - radius))
            elif self.family == "disconnector":
                blade_end = right if self.state == "closed" else 3.0
                blade_y = 0.0 if self.state == "closed" else -self.height * 0.34
                painter.drawLine(QPointF(left, 0), QPointF(blade_end, blade_y))
                mark_y = -self.height * 0.43
                mark_half = 4.5 * scene_scale
                painter.drawLine(QPointF(right - mark_half, mark_y),
                                 QPointF(right + mark_half, mark_y))
            else:
                blade_end = right if self.state == "closed" else 3.0
                blade_y = 0.0 if self.state == "closed" else -self.height * 0.34
                painter.drawLine(QPointF(left, 0), QPointF(blade_end, blade_y))
                ground_y = self.height * 0.28
                ground_x = right + 6.0 * scene_scale
                painter.drawLine(QPointF(ground_x, -ground_y),
                                 QPointF(ground_x, -ground_y / 2.0))
                painter.drawLine(QPointF(ground_x - 5.0 * scene_scale, -ground_y / 2.0),
                                 QPointF(ground_x + 5.0 * scene_scale, -ground_y / 2.0))
                painter.drawLine(QPointF(ground_x - 3.5 * scene_scale, 0),
                                 QPointF(ground_x + 3.5 * scene_scale, 0))
        elif self.family in {"generator", "source"}:
            radius = min(self.width, self.height) * 0.44
            painter.drawEllipse(QPointF(0.0, 0.0), radius, radius)
            glyph = "G" if self.family == "generator" else "~"
            painter.setPen(QPen(ink, 0.7 * scene_scale))
            font = _scene_font("STIX Two Text", 11.0, QFont.Weight.DemiBold)
            painter.setFont(font)
            metrics = QFontMetricsF(font)
            painter.drawText(
                QPointF(-metrics.horizontalAdvance(glyph) / 2.0, 0.28 * radius),
                glyph,
            )
        elif self.family in {"load", "capacitor", "reactor", "compensation"}:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            definition = get_symbol_definition(self.family)
            for primitive in definition.primitives:
                if primitive.kind == "circle":
                    px, py, radius = primitive.coordinates
                    painter.drawEllipse(QPointF(px, py), radius, radius)
                elif primitive.kind == "line":
                    x1, y1, x2, y2 = primitive.coordinates
                    painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))
            if definition.text_glyph:
                font = _scene_font("Segoe UI", 8.5, QFont.Weight.DemiBold)
                painter.setFont(font)
                metrics = QFontMetricsF(font)
                painter.setPen(QPen(ink, 0.6 * scene_scale))
                glyph = definition.text_glyph
                painter.drawText(
                    QPointF(-metrics.horizontalAdvance(glyph) / 2.0, metrics.ascent() * 0.34),
                    glyph,
                )
        else:
            # The unresolved/generic symbol is a rectangle with an explicit
            # question mark, matching the canonical vector renderer.
            painter.drawRect(QRectF(-self.width / 2.0, -self.height / 2.0,
                                    self.width, self.height))
            painter.setPen(QPen(ink, 0.7 * scene_scale))
            font = _scene_font("STIX Two Text", 6.0, QFont.Weight.Normal)
            painter.setFont(font)
            metrics = QFontMetricsF(font)
            painter.drawText(
                QPointF(-metrics.horizontalAdvance("?") / 2.0,
                        3.0 * scene_scale),
                "?",
            )
        if self.state in {"unresolved", "partial-data"}:
            badge_x = self.width / 2.0 + 4.0 * scene_scale
            badge_y = -self.height / 2.0 - 4.0 * scene_scale
            badge_radius = 4.0 * scene_scale
            painter.setPen(QPen(QColor("#D97706"), 0.8 * scene_scale))
            painter.setBrush(QBrush(QColor("#FFF7ED")))
            painter.drawEllipse(QPointF(badge_x, badge_y), badge_radius, badge_radius)
            mark = "?" if self.state == "unresolved" else "!"
            badge_font = _scene_font("Segoe UI", 6.0, QFont.Weight.Bold)
            painter.setFont(badge_font)
            metrics = QFontMetricsF(badge_font)
            painter.setPen(QPen(QColor("#9A3412"), 0.6 * scene_scale))
            painter.drawText(
                QPointF(badge_x - metrics.horizontalAdvance(mark) / 2.0,
                        badge_y + metrics.ascent() * 0.34),
                mark,
            )
        painter.restore()

    def mousePressEvent(self, event) -> None:
        self._drag_start = self.pos()
        self._dragging = True
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        try:
            super().mouseReleaseEvent(event)
            current = self.pos()
            if (current-self._drag_start).manhattanLength() > 0.1:
                self.move_committed.emit(
                    str(self.identifier), self._drag_start.x(), self._drag_start.y(),
                    current.x(), current.y(),
                )
        finally:
            self._dragging = False

    def itemChange(self, change, value):
        if (change is QGraphicsItem.GraphicsItemChange.ItemPositionChange
                and self._dragging and self.snap_enabled):
            return _snap_graphics_position(value, True, self.grid_spacing)
        if (
            change is QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged
            and not getattr(self, "_initializing", True)
        ):
            point = self.pos()
            self.moved.emit(
                str(self.identifier), point.x(), point.y()
            )
        return super().itemChange(change, value)


class SourceSymbol(QGraphicsObject):
    moved = Signal(str, float, float)
    move_committed = Signal(str, float, float, float, float)

    def __init__(
        self, identifier: UUID, name: str, subtype: str, *,
        snap_enabled: bool = True, grid_spacing: float = 20.0,
    ) -> None:
        super().__init__()
        self._initializing = True
        self.identifier = identifier
        self.name = name
        self.subtype = subtype
        self.snap_enabled = bool(snap_enabled)
        self.grid_spacing = float(grid_spacing)
        self._drag_start = QPointF()
        self._dragging = False
        self.setData(ROLE_ELEMENT, ("generator", str(identifier)))
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setZValue(15)
        self._initializing = False

    def boundingRect(self) -> QRectF:
        # The source name is painted below the glyph. It must be included in
        # the item's bounds or Qt clips/repaints it unpredictably while moving.
        return QRectF(-76.0, -54.0, 152.0, 108.0)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        del option, widget
        selected = self.isSelected()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        ink = QColor("#D97706" if selected else "#172033")
        scene_scale = LABEL_SCENE_UNITS_PER_PT
        radius = 44.0 * 0.44
        painter.setPen(QPen(ink, 0.7 * scene_scale))
        painter.setBrush(QBrush(QColor("#FFFFFF")))
        painter.drawEllipse(QPointF(0.0, 0.0), radius, radius)
        painter.setPen(QPen(ink, 0.7 * scene_scale))
        font = _scene_font("STIX Two Text", 11.0, QFont.Weight.DemiBold)
        painter.setFont(font)
        glyph = "G" if self.subtype == "synchronous_generator" else "~"
        metrics = QFontMetricsF(font)
        painter.drawText(QPointF(-metrics.horizontalAdvance(glyph) / 2.0, 0.28 * radius), glyph)

    def mousePressEvent(self, event) -> None:
        self._drag_start = self.pos()
        self._dragging = True
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        try:
            super().mouseReleaseEvent(event)
            current = self.pos()
            if (current - self._drag_start).manhattanLength() > 0.1:
                self.move_committed.emit(
                    str(self.identifier),
                    self._drag_start.x(),
                    self._drag_start.y(),
                    current.x(),
                    current.y(),
                )
        finally:
            self._dragging = False

    def itemChange(self, change, value):
        if (change is QGraphicsItem.GraphicsItemChange.ItemPositionChange
                and self._dragging and self.snap_enabled):
            return _snap_graphics_position(value, True, self.grid_spacing)
        if (
            change is QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged
            and not getattr(self, "_initializing", True)
        ):
            point = self.pos()
            self.moved.emit(
                str(self.identifier), point.x(), point.y()
            )
        return super().itemChange(change, value)


class DiagramLabelItem(QGraphicsTextItem):
    """Movable, independently editable annotation backed by workspace metadata."""

    changed = Signal(object)

    def __init__(self, label: EngineeringLabel) -> None:
        super().__init__(label.text)
        self.label_id = label.label_id
        self.owner_id = label.owner_id
        self.anchor = label.anchor
        self.font_family = _resolve_scene_font_family(label.font_family)
        self.size_pt = label.size_pt
        self.weight = label.weight
        self.color = label.color
        self.rotation_deg = label.rotation_deg
        self.visible_in_document = label.visible
        self.layer = label.layer
        self.priority = label.priority
        self.unit = label.unit
        self.number_format = label.number_format
        self._anchor_x = label.position.x
        self._baseline_y = label.position.y
        self._drag_start = QPointF()
        self.setData(ROLE_ELEMENT, ("label", str(label.label_id)))
        self.setDefaultTextColor(QColor(self.color))
        self.document().setDocumentMargin(0.0)
        self._apply_font()
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setZValue(35)
        self.setRotation(label.rotation_deg)
        self.document().contentsChanged.connect(self._on_text_changed)
        self._sync_scene_position()
        self.setVisible(label.visible)

    def _font_metrics(self) -> QFontMetricsF:
        return QFontMetricsF(self.font())

    def _sync_scene_position(self) -> None:
        metrics = self._font_metrics()
        width = self.boundingRect().width()
        x = self._anchor_x
        if self.anchor == "middle":
            x -= width / 2.0
        elif self.anchor == "end":
            x -= width
        self.setPos(QPointF(x, self._baseline_y - metrics.ascent()))

    def _anchor_position(self) -> tuple[float, float]:
        metrics = self._font_metrics()
        width = self.boundingRect().width()
        x = self.pos().x()
        if self.anchor == "middle":
            x += width / 2.0
        elif self.anchor == "end":
            x += width
        return x, self.pos().y() + metrics.ascent()

    def _apply_font(self) -> None:
        self.setFont(_scene_font(
            self.font_family,
            self.size_pt,
            {
                "normal": QFont.Weight.Normal,
                "medium": QFont.Weight.Medium,
                "semibold": QFont.Weight.DemiBold,
                "bold": QFont.Weight.Bold,
            }[self.weight],
        ))

    def _on_text_changed(self) -> None:
        self._sync_scene_position()
        self._emit_changed()

    def _emit_changed(self) -> None:
        if self.label_id is None:
            return
        x, y = self._anchor_position()
        # Keep the anchor in sync after a drag so later text edits do not jump
        # the annotation back to its original location.
        self._anchor_x, self._baseline_y = x, y
        self.changed.emit(DiagramLabelPlacement(
            label_id=self.label_id, owner_id=self.owner_id, text=self.toPlainText(),
            x=x, y=y, anchor=self.anchor, font_family=self.font_family,
            size_pt=self.size_pt, weight=self.weight, color=self.color,
            rotation_deg=self.rotation_deg,
            visible=self.visible_in_document, layer=self.layer, priority=self.priority,
            unit=self.unit, number_format=self.number_format,
        ))

    def _apply_style(self, *, size_pt: float | None = None, weight: str | None = None,
                     anchor: str | None = None, font_family: str | None = None,
                     color: str | None = None) -> None:
        if size_pt is not None:
            self.size_pt = max(4.0, min(18.0, float(size_pt)))
        if weight is not None:
            self.weight = weight
        if anchor is not None:
            self.anchor = anchor
        if font_family is not None:
            self.font_family = font_family
        if color is not None:
            self.color = color
            self.setDefaultTextColor(QColor(color))
        self._apply_font()
        self._sync_scene_position()
        self._emit_changed()

    def contextMenuEvent(self, event) -> None:
        menu = QMenu()
        increase = menu.addAction("Increase font size")
        decrease = menu.addAction("Decrease font size")
        menu.addSeparator()
        bold = menu.addAction("Toggle bold")
        alignment = menu.addMenu("Text anchor")
        align_start = alignment.addAction("Left")
        align_middle = alignment.addAction("Center")
        align_end = alignment.addAction("Right")
        fonts = menu.addMenu("Font family")
        font_actions = [
            (fonts.addAction(name), name)
            for name in _available_label_font_families()
        ]
        colors = menu.addMenu("Text color")
        color_actions = [
            (colors.addAction(name), value)
            for name, value in (
                ("Engineering ink", "#172033"),
                ("Graphite", "#526273"),
                ("Blue annotation", "#1D4ED8"),
                ("Warning amber", "#8A5A12"),
                ("Muted gray", "#667085"),
            )
        ]
        selected = menu.exec(event.screenPos())
        if selected == increase:
            self._apply_style(size_pt=self.size_pt + 0.5)
        elif selected == decrease:
            self._apply_style(size_pt=self.size_pt - 0.5)
        elif selected == bold:
            self._apply_style(weight="normal" if self.weight == "bold" else "bold")
        elif selected == align_start:
            self._apply_style(anchor="start")
        elif selected == align_middle:
            self._apply_style(anchor="middle")
        elif selected == align_end:
            self._apply_style(anchor="end")
        else:
            font_family = next((value for action, value in font_actions if selected == action), None)
            color = next((value for action, value in color_actions if selected == action), None)
            if font_family is not None:
                self._apply_style(font_family=font_family)
            elif color is not None:
                self._apply_style(color=color)
        event.accept()

    def mousePressEvent(self, event) -> None:
        self._drag_start = self.pos()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        super().mouseReleaseEvent(event)
        if (self.pos() - self._drag_start).manhattanLength() > 0.1:
            self._emit_changed()


class _BranchSymbolSignals(QObject):
    """QObject-backed signals for a QGraphicsPathItem (which is not a QObject)."""

    moved = Signal(str, float, float)
    move_committed = Signal(str, float, float, float, float)


class BranchSymbol(QGraphicsPathItem):
    """Movable branch path with QObject-owned signals.

    QGraphicsPathItem inherits QGraphicsItem, not QObject. Declaring Signal
    descriptors directly on this class therefore does not create bound Qt
    signals; ``emit`` fails when ``itemChange`` runs. A small QObject signal
    carrier keeps the graphics item type and its public signal API intact.
    """

    def __init__(
        self, identifier: UUID, name: str, from_point: QPointF, to_point: QPointF, label: str,
        *, snap_enabled: bool = True, grid_spacing: float = 20.0,
        state: str | None = None,
    ) -> None:
        super().__init__()
        self._branch_signals = _BranchSymbolSignals()
        self._initializing = True
        self.identifier = identifier
        self.name = name
        self.state = state
        self.snap_enabled = bool(snap_enabled)
        self.grid_spacing = float(grid_spacing)
        self._drag_start = QPointF()
        self._dragging = False
        self.setData(ROLE_ELEMENT, ("line", str(identifier)))
        self.setZValue(2)
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setPen(QPen(QColor("#172033"), 0.72 * LABEL_SCENE_UNITS_PER_PT,
                         Qt.PenStyle.SolidLine, Qt.PenCapStyle.SquareCap))
        self.setBrush(Qt.BrushStyle.NoBrush)
        self.set_endpoints(from_point, to_point)
        self.label_item = QGraphicsSimpleTextItem(label)
        self.label_item.setBrush(QBrush(QColor("#0F172A")))
        self.label_item.setFont(QFont("Segoe UI", 8, QFont.Weight.DemiBold))
        self.label_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
        self.label_item.setZValue(5)
        self._initializing = False

    def boundingRect(self) -> QRectF:
        bounds = super().boundingRect()
        if self.state in {"unresolved", "partial-data"}:
            bounds = bounds.united(QRectF(-30.0, -15.0, 30.0, 30.0))
        return bounds

    def paint(self, painter: QPainter, option, widget=None) -> None:
        super().paint(painter, option, widget)
        if self.state not in {"unresolved", "partial-data"}:
            return
        path_bounds = self.path().boundingRect()
        if path_bounds.height() >= path_bounds.width():
            center = QPointF(-15.0, 0.0)
        else:
            center = QPointF(0.0, -15.0)
        radius = 5.0 * LABEL_SCENE_UNITS_PER_PT
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(QColor("#D97706"), 0.8 * LABEL_SCENE_UNITS_PER_PT))
        painter.setBrush(QBrush(QColor("#FFF7ED")))
        painter.drawEllipse(center, radius, radius)
        mark = "?" if self.state == "unresolved" else "!"
        font = _scene_font("Segoe UI", 6.0, QFont.Weight.Bold)
        painter.setFont(font)
        metrics = QFontMetricsF(font)
        painter.setPen(QPen(QColor("#9A3412"), 0.6 * LABEL_SCENE_UNITS_PER_PT))
        painter.drawText(
            QPointF(center.x() - metrics.horizontalAdvance(mark) / 2.0,
                    center.y() + metrics.ascent() * 0.34),
            mark,
        )
        painter.restore()

    @property
    def moved(self):
        """Bound Qt signal emitted while the branch is being moved."""
        return self._branch_signals.moved

    @property
    def move_committed(self):
        """Bound Qt signal emitted when a branch drag is committed."""
        return self._branch_signals.move_committed

    def set_endpoints(self, from_point: QPointF, to_point: QPointF) -> None:
        # Keep branch geometry in local coordinates so the complete piece of
        # equipment can be moved without breaking either terminal identity.
        center = (from_point + to_point) / 2.0
        self.setPos(center)
        path = QPainterPath(from_point - center)
        path.lineTo(to_point - center)
        self.setPath(path)
        if hasattr(self, "label_item"):
            self.label_item.setPos((from_point + to_point) / 2.0 - center + QPointF(7.0, -19.0))

    def mousePressEvent(self, event) -> None:
        self._drag_start = self.pos()
        self._dragging = True
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        try:
            super().mouseReleaseEvent(event)
            current = self.pos()
            if (current - self._drag_start).manhattanLength() > 0.1:
                self.move_committed.emit(
                    str(self.identifier), self._drag_start.x(), self._drag_start.y(),
                    current.x(), current.y(),
                )
        finally:
            self._dragging = False

    def itemChange(self, change, value):
        if (change is QGraphicsItem.GraphicsItemChange.ItemPositionChange
                and self._dragging and self.snap_enabled):
            return _snap_graphics_position(value, True, self.grid_spacing)
        if (
            change is QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged
            and not getattr(self, "_initializing", True)
        ):
            point = self.pos()
            self._branch_signals.moved.emit(
                str(self.identifier), point.x(), point.y()
            )
        return super().itemChange(change, value)


class NetworkCanvasView(QGraphicsView):
    """Interactive one-line diagram canvas with independent presentation coordinates."""

    element_selected = Signal(str, str)
    layout_changed = Signal(str, float, float)
    position_committed = Signal(str, float, float, float, float)
    rotate_symbol_requested = Signal(str, float)
    remove_symbol_requested = Signal()
    create_bus_requested = Signal()
    load_template_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        # Make the scene a QObject child of the view.  Its lifetime is then
        # bounded by the canvas instead of depending on an unparented wrapper.
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._selection_callback_connected = True
        self._workspace: NetworkWorkspace | None = None
        self._command_service = None
        self._operating_topology = None
        self._operating_projection_error: str | None = None
        self._bus_items: dict[str, BusSymbol] = {}
        self._source_items: dict[str, SourceSymbol] = {}
        self._equipment_items: dict[str, CanonicalEquipmentSymbol] = {}
        self._branch_items: dict[str, BranchSymbol] = {}
        self._conductor_items: dict[str, QGraphicsPathItem] = {}
        self._junction_items: dict[str, QGraphicsEllipseItem] = {}
        self._terminal_route_specs: dict[str, tuple[UUID, UUID, float, float, float, float]] = {}
        self._terminal_projected_points: dict[str, QPointF] = {}
        self._last_layout_positions: dict[str, tuple[float, float]] = {}
        self._label_items: dict[str, DiagramLabelItem] = {}
        self._label_models: dict[str, EngineeringLabel] = {}
        self._draft_symbol_items: dict[str, QETSymbolItem] = {}
        self._symbol_links: dict[str, list[QGraphicsPathItem]] = {}
        self._symbol_definitions: dict[str, SymbolDefinition] = {}
        # Drawing-only QET assets are reference material, never default SLD content.
        self._source_candidates_visible = False
        self._source_candidate_selection_when_hidden: set[str] = set()
        self._grid_visible = True
        self._snap_enabled = True
        self._grid_spacing = 20.0
        self._middle_pan = False
        self._pan_last = None
        self._applying_position = False
        # QGraphicsView receives keyboard shortcuts through its viewport. Make
        # both the view and viewport explicitly focusable so mouse selection and
        # keyboard commands have a deterministic focus target on Windows.
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.viewport().setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.BoundingRectViewportUpdate)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setRubberBandSelectionMode(Qt.ItemSelectionMode.IntersectsItemShape)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setBackgroundBrush(QColor("#FFFFFF"))
        self._scene.selectionChanged.connect(self._emit_selection)
        self._build_empty_state()

    def _build_empty_state(self) -> None:
        """Present a deliberate first-run state instead of an empty graph-paper void."""
        card = QFrame(self.viewport())
        card.setObjectName("CanvasWelcomeCard")
        card.setMinimumWidth(300)
        card.setMaximumWidth(460)
        content = QVBoxLayout(card)
        content.setContentsMargins(26, 24, 26, 22)
        content.setSpacing(10)

        eyebrow = QLabel("POWER SYSTEM MODEL")
        eyebrow.setObjectName("CanvasWelcomeEyebrow")
        title = QLabel("Start with the network.")
        title.setObjectName("CanvasWelcomeTitle")
        title.setWordWrap(True)
        description = QLabel(
            "Add busbars and equipment to establish the electrical model. "
            "The one-line drawing is arranged independently from the calculation topology."
        )
        description.setObjectName("CanvasWelcomeDescription")
        description.setWordWrap(True)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        create_bus = QPushButton("Add first AC bus")
        create_bus.setObjectName("PrimaryAction")
        create_bus.setMinimumHeight(38)
        create_bus.clicked.connect(self.create_bus_requested.emit)
        load_reference = QPushButton("Open reference case")
        load_reference.setObjectName("SecondaryAction")
        load_reference.setMinimumHeight(38)
        load_reference.clicked.connect(self.load_template_requested.emit)
        actions.addWidget(create_bus, 1)
        actions.addWidget(load_reference, 1)

        help_line = QLabel("Wheel to zoom  ·  Middle-drag to pan  ·  Ctrl+0 to fit")
        help_line.setObjectName("CanvasWelcomeHint")

        content.addWidget(eyebrow)
        content.addWidget(title)
        content.addWidget(description)
        content.addSpacing(4)
        content.addLayout(actions)
        content.addWidget(help_line)
        self._empty_state = card
        self._empty_state.hide()

    def _update_empty_state(self) -> None:
        if self._workspace is None:
            empty = True
        else:
            empty = not (
                self._workspace.network.buses
                or self._workspace.network.equipment
                or self._workspace.diagram_symbols
            )
        self._empty_state.setVisible(empty)
        self._position_empty_state()

    def _position_empty_state(self) -> None:
        if not hasattr(self, "_empty_state"):
            return
        viewport = self.viewport().rect()
        card = self._empty_state.sizeHint()
        width = min(460, max(320, viewport.width() - 36))
        height = min(card.height(), max(160, viewport.height() - 36))
        self._empty_state.setGeometry(
            (viewport.width() - width) // 2,
            (viewport.height() - height) // 2,
            width,
            height,
        )
        if self._empty_state.isVisible():
            self._empty_state.raise_()

    def set_command_service(self, command_service) -> None:
        """Bind the shared application command facade used by Python and the UI."""
        self._command_service = command_service

    def set_workspace(self, workspace: NetworkWorkspace) -> None:
        self._workspace = workspace
        self._snap_enabled = workspace.snap_enabled
        self._grid_spacing = float(workspace.grid_spacing)
        self.render_network()

    def render_network(self) -> None:
        self._scene.clear()
        self._bus_items.clear()
        self._source_items.clear()
        self._equipment_items.clear()
        self._branch_items.clear()
        self._conductor_items.clear()
        self._junction_items.clear()
        self._terminal_route_specs.clear()
        self._terminal_projected_points.clear()
        self._last_layout_positions.clear()
        self._label_items.clear()
        self._label_models.clear()
        self._draft_symbol_items.clear()
        self._symbol_links.clear()
        if self._workspace is None:
            self._operating_topology = None
            self._operating_projection_error = None
            self._scene.setSceneRect(QRectF(-1200.0, -900.0, 2400.0, 1800.0))
            self._update_empty_state()
            return
        self._operating_topology = None
        self._operating_projection_error = None
        if self._workspace.active_operating_scenario is not None:
            try:
                self._operating_topology = analyze_workspace(self._workspace)
            except (KeyError, TypeError, ValueError, RuntimeError) as exc:
                self._operating_projection_error = str(exc)
        try:
            document = project_network_to_diagram(self._workspace)
        except DiagramProjectionError as exc:
            self._projection_error = str(exc)
            error_item = QGraphicsSimpleTextItem(f"DIAGRAM PROJECTION ERROR: {exc}")
            error_item.setBrush(QBrush(QColor("#B91C1C")))
            error_item.setPos(24.0, 24.0)
            self._scene.addItem(error_item)
            self._scene.setSceneRect(QRectF(0, 0, 1100, 500))
            self._update_empty_state()
            return
        self._projection_error = None
        network = self._workspace.network
        operating_buses = (
            {item.bus_id: item for item in self._operating_topology.buses}
            if self._operating_topology is not None else {}
        )
        operating_equipment = (
            {item.equipment_id: item for item in self._operating_topology.equipment}
            if self._operating_topology is not None else {}
        )
        active_scenario = self._workspace.active_operating_scenario
        bus_positions = {str(item.bus_id): QPointF(item.center.x, item.center.y)
                         for item in document.buses}
        projected_bus_by_id = {str(item.bus_id): item for item in document.buses}
        symbol_model = {item.equipment_id: item for item in document.symbols}
        equipment_by_terminal = {
            terminal.id: equipment
            for equipment in network.equipment for terminal in equipment.terminals
        }

        # Conductors are generated only from canonical terminal-to-bus connections.
        for conductor in document.conductors:
            if len(conductor.points) < 2:
                continue
            terminal_point = conductor.points[-1]
            equipment = equipment_by_terminal[conductor.terminal_id]
            projected = symbol_model[equipment.id]
            dx = terminal_point.x - projected.center.x
            dy = terminal_point.y - projected.center.y
            if projected.family == "line":
                # BranchSymbol stores its already-oriented line geometry locally.
                local_x, local_y, route_orientation = dx, dy, 0.0
            else:
                angle = math.radians(projected.orientation_deg)
                local_x = dx * math.cos(angle) + dy * math.sin(angle)
                local_y = -dx * math.sin(angle) + dy * math.cos(angle)
                route_orientation = projected.orientation_deg
            projected_bus = projected_bus_by_id[str(conductor.bus_id)]
            bus_angle = math.radians(projected_bus.orientation_deg)
            bus_axis_x, bus_axis_y = math.cos(bus_angle), math.sin(bus_angle)
            tap_delta_x = conductor.points[0].x - projected_bus.center.x
            tap_delta_y = conductor.points[0].y - projected_bus.center.y
            tap_axis_offset = tap_delta_x * bus_axis_x + tap_delta_y * bus_axis_y
            self._terminal_route_specs[str(conductor.terminal_id)] = (
                conductor.bus_id, equipment.id, local_x, local_y, route_orientation,
                tap_axis_offset,
            )
            self._terminal_projected_points[str(conductor.terminal_id)] = QPointF(
                terminal_point.x, terminal_point.y
            )
            path = QPainterPath(QPointF(conductor.points[0].x, conductor.points[0].y))
            for point in conductor.points[1:]:
                path.lineTo(QPointF(point.x, point.y))
            link = QGraphicsPathItem(path)
            operational_record = operating_equipment.get(equipment.id)
            conductor_color = (
                QColor("#15803D")
                if operational_record is not None and operational_record.contributes_to_connectivity
                else QColor("#94A3B8")
                if operational_record is not None
                else QColor("#334155")
            )
            link.setPen(QPen(conductor_color, 0.72 * LABEL_SCENE_UNITS_PER_PT,
                             Qt.PenStyle.SolidLine))
            link.setZValue(3)
            self._scene.addItem(link)
            self._conductor_items[str(conductor.terminal_id)] = link

        for bus in network.buses:
            projected = next(item for item in document.buses if item.bus_id == bus.id)
            bar_length = max(projected.bounds.width, projected.bounds.height)
            bus_operational = operating_buses.get(bus.id)
            item = BusSymbol(
                bus.id, bus.name, bus.nominal_voltage.value_kv,
                self._snap_enabled, bus.kind, bar_length,
                bus_operational.state if bus_operational is not None else None,
                bus_operational.grounded if bus_operational is not None else False,
                grid_spacing=self._grid_spacing,
            )
            item.setPos(bus_positions[str(bus.id)])
            self._last_layout_positions[str(bus.id)] = (item.pos().x(), item.pos().y())
            item.setTransformOriginPoint(QPointF(0.0, 0.0))
            item.setRotation(projected.orientation_deg)
            item.moved.connect(self._on_layout_changed)
            item.move_committed.connect(self.position_committed.emit)
            self._scene.addItem(item)
            self._bus_items[str(bus.id)] = item

        # Show an explicit node at every canonical terminal-to-bus attachment.
        # SVG/PDF already render these model-derived tap markers; keeping the
        # Qt scene identical also makes a T-connection distinguishable from a
        # visual crossing. Each dot follows its own connection during dragging.
        bus_kind_by_id = {item.id: item.kind for item in network.buses}
        for conductor in document.conductors:
            if (
                not conductor.points
                or bus_kind_by_id.get(conductor.bus_id) is BusKind.CONNECTION_NODE
            ):
                continue
            tap_radius = 1.7 * LABEL_SCENE_UNITS_PER_PT
            marker = QGraphicsEllipseItem(
                -tap_radius, -tap_radius, 2.0 * tap_radius, 2.0 * tap_radius
            )
            marker.setPen(QPen(Qt.PenStyle.NoPen))
            marker.setBrush(QBrush(QColor("#172033")))
            marker.setZValue(24)
            marker.setPos(QPointF(conductor.points[0].x, conductor.points[0].y))
            self._scene.addItem(marker)
            self._junction_items[str(conductor.terminal_id)] = marker

        for equipment in network.equipment:
            projected = symbol_model[equipment.id]
            if projected.family == "line" and len(projected.terminal_ids) == 2:
                # The branch spine is drawn between the canonical equipment
                # terminal coordinates; bus-to-terminal drops were already
                # projected from the exact terminal-to-bus connection records.
                p1 = QPointF(projected.terminal_points[0].x, projected.terminal_points[0].y)
                p2 = QPointF(projected.terminal_points[1].x, projected.terminal_points[1].y)
                line = BranchSymbol(
                    equipment.id, equipment.name, p1, p2, "",
                    snap_enabled=self._snap_enabled, grid_spacing=self._grid_spacing,
                    state=projected.state,
                )
                self._scene.addItem(line)
                self._branch_items[str(equipment.id)] = line
                self._last_layout_positions[str(equipment.id)] = (line.pos().x(), line.pos().y())
                line.moved.connect(self._on_layout_changed)
                line.move_committed.connect(self.position_committed.emit)
            elif projected.family == "source" and isinstance(equipment, (EquivalentSource, SynchronousGenerator)):
                symbol = SourceSymbol(
                    equipment.id, equipment.name,
                    "equivalent_source" if isinstance(equipment, EquivalentSource)
                    else "synchronous_generator",
                    snap_enabled=self._snap_enabled, grid_spacing=self._grid_spacing,
                )
                symbol.setPos(QPointF(projected.center.x, projected.center.y))
                self._last_layout_positions[str(equipment.id)] = (symbol.pos().x(), symbol.pos().y())
                symbol.moved.connect(self._on_layout_changed)
                symbol.move_committed.connect(self.position_committed.emit)
                self._scene.addItem(symbol)
                self._source_items[str(equipment.id)] = symbol
            else:
                projected_label = next(
                    (item.text for item in document.labels if item.owner_id == equipment.id),
                    equipment.name,
                )
                operational_record = operating_equipment.get(equipment.id)
                simulated_position = (
                    operational_record.switch_position.value
                    if operational_record is not None and operational_record.switch_position is not None
                    else projected.state
                )
                symbol = CanonicalEquipmentSymbol(
                    equipment.id, equipment.name, projected.family, simulated_position,
                    projected.width, projected.height, projected.orientation_deg,
                    projected_label,
                    operating_override=(
                        active_scenario is not None
                        and equipment.id in active_scenario.switch_positions
                    ),
                    snap_enabled=self._snap_enabled,
                    grid_spacing=self._grid_spacing,
                )
                symbol.setPos(QPointF(projected.center.x, projected.center.y))
                self._last_layout_positions[str(equipment.id)] = (symbol.pos().x(), symbol.pos().y())
                symbol.moved.connect(self._on_layout_changed)
                symbol.move_committed.connect(self.position_committed.emit)
                self._scene.addItem(symbol)
                self._equipment_items[str(equipment.id)] = symbol

        for label in document.labels:
            label_key = str(label.label_id) if label.label_id else f"{label.owner_id}:{label.text}"
            self._label_models[label_key] = label
            item = DiagramLabelItem(label)
            item.changed.connect(self._commit_diagram_label)
            self._scene.addItem(item)
            self._label_items[label_key] = item

        for placement in self._workspace.diagram_symbols.values():
            definition = self._symbol_definitions.get(placement.asset_id)
            if definition is None:
                continue
            self._add_draft_symbol_item(placement, definition)
        self._render_mapped_symbol_connections()
        if self._snap_enabled:
            # Normalize only existing manual overrides; auto-layout coordinates remain derived.
            for collection in (self._bus_items, self._source_items, self._equipment_items, self._branch_items):
                for identifier, graphics_item in collection.items():
                    key = UUID(identifier)
                    if key in self._workspace.diagram_positions:
                        point = graphics_item.pos()
                        self._workspace.diagram_positions[key] = (float(point.x()), float(point.y()))
            for identifier, graphics_item in self._draft_symbol_items.items():
                placement = self._workspace.diagram_symbols.get(UUID(identifier))
                if placement is not None:
                    point = graphics_item.pos()
                    self._workspace.update_diagram_symbol(
                        placement.instance_id, x=float(point.x()), y=float(point.y())
                    )
        self._update_branch_geometry()
        items_rect = self._scene.itemsBoundingRect()
        self._scene.setSceneRect(items_rect.adjusted(-120, -100, 180, 120)
                                 if not items_rect.isEmpty()
                                 else QRectF(-1200.0, -900.0, 2400.0, 1800.0))
        if active_scenario is not None:
            banner_text = (
                f"OPERATING SCENARIO: {active_scenario.name}  |  SIMULATION ONLY"
                if self._operating_projection_error is None
                else f"OPERATING SCENARIO ERROR: {self._operating_projection_error}"
            )
            banner = QGraphicsSimpleTextItem(banner_text)
            banner.setBrush(QBrush(QColor("#1D4ED8" if self._operating_projection_error is None else "#B91C1C")))
            banner.setFont(_scene_font("Segoe UI", 8.0, QFont.Weight.DemiBold))
            banner.setPos(self._scene.sceneRect().left() + 20.0, self._scene.sceneRect().top() + 12.0)
            banner.setZValue(100)
            self._scene.addItem(banner)
        self._update_empty_state()
        self.viewport().update()

    def _commit_diagram_label(self, label: DiagramLabelPlacement) -> None:
        if self._workspace is None or not isinstance(label, DiagramLabelPlacement):
            return
        if not label.text.strip():
            return
        if self._command_service is not None:
            self._command_service.upsert_label(label)
        else:
            self._workspace.upsert_diagram_label(label)
        self._label_models[str(label.label_id)] = EngineeringLabel(
            label.owner_id, label.text, Point(label.x, label.y),
            label.anchor, label.label_id, label.font_family, label.size_pt, label.weight,
            label.color, label.rotation_deg, label.visible, label.layer, label.priority,
            label.unit, label.number_format,
        )

    def _commit_equipment_label(self, identifier: str, label: str) -> None:
        if self._workspace is None or not label.strip():
            return
        equipment_id = UUID(identifier)
        current = next(
            (item for item in self._workspace.diagram_symbols.values()
             if item.equipment_id == equipment_id), None
        )
        symbol = self._equipment_items.get(identifier)
        if symbol is None:
            return
        if current is None:
            placement = DiagramSymbolPlacement.create(
                f"PFA-CANONICAL-{symbol.family}", symbol.pos().x(), symbol.pos().y(),
                symbol.orientation_deg, equipment_id=equipment_id, label=label.strip(),
            )
        else:
            placement = DiagramSymbolPlacement(
                current.instance_id, current.asset_id, symbol.pos().x(), symbol.pos().y(),
                symbol.orientation_deg, equipment_id, current.terminal_mappings, label.strip(),
            )
        if self._command_service is not None:
            self._command_service.upsert_symbol(placement)
        else:
            self._workspace.diagram_symbols[placement.instance_id] = placement

    def set_symbol_definitions(self, definitions: dict[str, SymbolDefinition]) -> None:
        self._symbol_definitions = dict(definitions)
        if self._workspace is not None:
            self.render_network()

    def insert_diagram_symbol(
        self, placement: DiagramSymbolPlacement, definition: SymbolDefinition
    ) -> None:
        if placement.asset_id != definition.provenance.asset_id:
            raise ValueError("Placement asset_id does not match the source symbol definition.")
        self._symbol_definitions[placement.asset_id] = definition
        self._add_draft_symbol_item(placement, definition)
        self._scene.setSceneRect(self._scene.itemsBoundingRect().adjusted(-180, -160, 180, 160))
        self._update_empty_state()

    def _add_draft_symbol_item(
        self, placement: DiagramSymbolPlacement, definition: SymbolDefinition
    ) -> QETSymbolItem:
        item = QETSymbolItem(
            definition,
            interactive=True,
            instance_id=placement.instance_id,
            require_connectable=bool(placement.terminal_mappings),
            rotation_deg=placement.rotation_deg,
            snap_enabled=self._snap_enabled,
            grid_spacing=self._grid_spacing,
        )
        item.setPos(QPointF(placement.x, placement.y))
        if placement.equipment_id is not None:
            item.setData(ROLE_ELEMENT, ("equipment", str(placement.equipment_id)))
        item.position_committed.connect(self.position_committed.emit)
        item.setZValue(30)
        item.setVisible(self._source_candidates_visible)
        self._scene.addItem(item)
        if placement.label:
            annotation = QGraphicsSimpleTextItem(placement.label, item)
            annotation.setBrush(QBrush(QColor("#475569")))
            annotation.setFont(QFont("Segoe UI", 8, QFont.Weight.DemiBold))
            annotation.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
            bounds = item.boundingRect()
            annotation.setPos(bounds.right() + 8.0, bounds.center().y() - 8.0)
        self._draft_symbol_items[str(placement.instance_id)] = item
        self._scene.clearSelection()
        item.setSelected(True)
        return item

    def _render_mapped_symbol_connections(self) -> None:
        """Render wires only for explicit symbol-pin to equipment-terminal mappings."""
        if self._workspace is None:
            return
        network = self._workspace.network
        connections = {item.terminal_id: item.bus_id for item in network.connections}
        for placement in self._workspace.diagram_symbols.values():
            if not placement.equipment_id or not placement.terminal_mappings:
                continue
            symbol_item = self._draft_symbol_items.get(str(placement.instance_id))
            if symbol_item is None:
                continue
            link_items: list[QGraphicsPathItem] = []
            for source_terminal_id, equipment_terminal_id in placement.terminal_mappings:
                bus_id = connections.get(equipment_terminal_id)
                bus_item = self._bus_items.get(str(bus_id)) if bus_id else None
                if bus_item is None:
                    continue
                terminal_point = symbol_item.mapToScene(
                    symbol_item.terminal_position(source_terminal_id)
                )
                bus_point = bus_item.connection_point(terminal_point)
                path = QPainterPath(terminal_point)
                if abs(terminal_point.x() - bus_point.x()) > 0.5:
                    elbow_y = (terminal_point.y() + bus_point.y()) / 2.0
                    path.lineTo(QPointF(terminal_point.x(), elbow_y))
                    path.lineTo(QPointF(bus_point.x(), elbow_y))
                path.lineTo(bus_point)
                link = QGraphicsPathItem(path)
                link.setPen(QPen(QColor("#334155"), 1.8, Qt.PenStyle.SolidLine))
                link.setZValue(8)
                link.setVisible(self._source_candidates_visible)
                self._scene.addItem(link)
                link_items.append(link)
            self._symbol_links[str(placement.instance_id)] = link_items

    def _update_symbol_connection_geometry(self) -> None:
        if self._workspace is None:
            return
        for placement in self._workspace.diagram_symbols.values():
            links = self._symbol_links.get(str(placement.instance_id), [])
            if not links or not placement.equipment_id:
                continue
            symbol_item = self._draft_symbol_items.get(str(placement.instance_id))
            if symbol_item is None:
                continue
            connection_map = {
                item.terminal_id: item.bus_id for item in self._workspace.network.connections
            }
            for link, (source_terminal_id, equipment_terminal_id) in zip(
                links, placement.terminal_mappings, strict=False
            ):
                bus_id = connection_map.get(equipment_terminal_id)
                bus_item = self._bus_items.get(str(bus_id)) if bus_id else None
                if bus_item is None:
                    continue
                terminal_point = symbol_item.mapToScene(
                    symbol_item.terminal_position(source_terminal_id)
                )
                bus_point = bus_item.connection_point(terminal_point)
                path = QPainterPath(terminal_point)
                if abs(terminal_point.x() - bus_point.x()) > 0.5:
                    elbow_y = (terminal_point.y() + bus_point.y()) / 2.0
                    path.lineTo(QPointF(terminal_point.x(), elbow_y))
                    path.lineTo(QPointF(bus_point.x(), elbow_y))
                path.lineTo(bus_point)
                link.setPath(path)

    def source_candidate_items(self) -> tuple[QETSymbolItem, ...]:
        """Return source-library placements, never electrical equipment items."""
        return tuple(self._draft_symbol_items.values())

    def set_source_candidate_visibility(self, visible: bool) -> None:
        visible = bool(visible)
        if visible == self._source_candidates_visible:
            return

        if not visible:
            # Qt deselects QGraphicsItems when they become invisible. Preserve the
            # current selection so hiding and restoring the source layer does not
            # silently disable the next rotate, delete or properties command.
            self._source_candidate_selection_when_hidden = {
                key for key, item in self._draft_symbol_items.items() if item.isSelected()
            }
            self._source_candidates_visible = False
            for item in self._draft_symbol_items.values():
                item.setVisible(False)
            for links in self._symbol_links.values():
                for link in links:
                    link.setVisible(False)
            return

        self._source_candidates_visible = True
        selected_ids = self._source_candidate_selection_when_hidden
        self._source_candidate_selection_when_hidden = set()
        for key, item in self._draft_symbol_items.items():
            item.setVisible(True)
            if key in selected_ids:
                item.setSelected(True)
        for links in self._symbol_links.values():
            for link in links:
                link.setVisible(True)

    def remove_diagram_symbol(self, instance_id: UUID) -> None:
        key = str(instance_id)
        self._source_candidate_selection_when_hidden.discard(key)
        item = self._draft_symbol_items.pop(key, None)
        for link in self._symbol_links.pop(key, []):
            self._scene.removeItem(link)
        if item is not None:
            self._scene.removeItem(item)
            items_rect = self._scene.itemsBoundingRect()
            self._scene.setSceneRect(
                items_rect.adjusted(-180, -160, 180, 160)
                if not items_rect.isEmpty()
                else QRectF(-1200.0, -900.0, 2400.0, 1800.0)
            )
            self._update_empty_state()

    def selected_bus_symbol(self) -> tuple[UUID, float] | None:
        for item in self._scene.selectedItems():
            if isinstance(item, BusSymbol) and item.kind is BusKind.BUSBAR:
                return item.identifier, item.rotation() % 360.0
        return None

    def set_bus_rotation(self, bus_id: UUID, rotation_deg: float) -> None:
        item = self._bus_items.get(str(bus_id))
        if item is None:
            raise KeyError(f"Bus '{bus_id}' is not rendered.")
        item.setRotation(float(rotation_deg) % 360.0)
        self._update_branch_geometry()
        self._update_symbol_connection_geometry()
        self._scene.setSceneRect(self._scene.itemsBoundingRect().adjusted(-180, -160, 180, 160))
        self.viewport().update()

    def selected_diagram_symbol(self) -> tuple[UUID, float] | None:
        for item in self._scene.selectedItems():
            if isinstance(item, QETSymbolItem) and item.instance_id is not None:
                return item.instance_id, item.rotation() % 360.0
        return None

    def set_diagram_symbol_rotation(self, instance_id: UUID, rotation_deg: float) -> None:
        item = self._draft_symbol_items.get(str(instance_id))
        if item is None:
            raise KeyError(f"Diagram symbol instance '{instance_id}' is not rendered.")
        item.setRotation(float(rotation_deg) % 360.0)
        self._scene.setSceneRect(self._scene.itemsBoundingRect().adjusted(-180, -160, 180, 160))
        self._update_symbol_connection_geometry()
        self.viewport().update()

    def _update_branch_geometry(self) -> None:
        """Route terminal wires, preferring independent straight bus drops."""
        if self._workspace is None:
            return

        resolved: list[tuple[str, BusSymbol, QPointF, float]] = []
        desired_offsets_by_bus: dict[str, list[tuple[str, float]]] = {}
        for terminal_id, (
            bus_id, equipment_id, local_x, local_y, angle_deg, reserved_tap_offset
        ) in self._terminal_route_specs.items():
            bus_key = str(bus_id)
            bus_item = self._bus_items.get(bus_key)
            if bus_item is None or terminal_id not in self._conductor_items:
                continue
            equipment_item = (
                self._source_items.get(str(equipment_id))
                or self._equipment_items.get(str(equipment_id))
                or self._branch_items.get(str(equipment_id))
            )
            if equipment_item is not None:
                item_angle = (
                    0.0 if isinstance(equipment_item, BranchSymbol)
                    else float(getattr(equipment_item, "orientation_deg", angle_deg))
                )
                angle = math.radians(item_angle)
                terminal_point = equipment_item.pos() + QPointF(
                    local_x * math.cos(angle) - local_y * math.sin(angle),
                    local_x * math.sin(angle) + local_y * math.cos(angle),
                )
            else:
                # Branches without a movable graphics item retain their projected pin.
                terminal_point = self._terminal_projected_points.get(terminal_id)
                if terminal_point is None:
                    continue

            bus_angle = math.radians(bus_item.rotation())
            axis_x, axis_y = math.cos(bus_angle), math.sin(bus_angle)
            dx = terminal_point.x() - bus_item.pos().x()
            dy = terminal_point.y() - bus_item.pos().y()
            desired_offset = dx * axis_x + dy * axis_y
            if bus_item.kind is BusKind.BUSBAR:
                desired_offset = max(
                    -bus_item.width / 2.0,
                    min(bus_item.width / 2.0, desired_offset),
                )
            desired_offsets_by_bus.setdefault(bus_key, []).append(
                (terminal_id, desired_offset)
            )
            resolved.append((terminal_id, bus_item, terminal_point, reserved_tap_offset))

        # A wire can be a single perpendicular segment when its projected tap
        # does not collide with another terminal on the same bus. If two
        # terminals compete for nearly the same tap, retain their reserved bays.
        straight_terminal_ids: set[str] = set()
        for entries in desired_offsets_by_bus.values():
            straight_terminal_ids.update(
                select_straight_bus_taps(entries, minimum_separation=18.0)
            )

        for terminal_id, bus_item, terminal_point, reserved_tap_offset in resolved:
            tap_offset = None if terminal_id in straight_terminal_ids else reserved_tap_offset
            bus_point = bus_item.connection_point(terminal_point, tap_offset)
            junction = self._junction_items.get(terminal_id)
            if junction is not None:
                junction.setPos(bus_point)

            route = perpendicular_bay_route(
                Point(bus_point.x(), bus_point.y()),
                Point(terminal_point.x(), terminal_point.y()),
                bus_item.rotation(),
                clearance=18.0,
                minimum_stub=6.0,
            )
            if route:
                path = QPainterPath(QPointF(route[0].x, route[0].y))
                for point in route[1:]:
                    path.lineTo(QPointF(point.x, point.y))
                self._conductor_items[terminal_id].setPath(path)
        self._update_symbol_connection_geometry()

    def _on_layout_changed(self, identifier: str, x: float, y: float) -> None:
        if self._workspace is None or self._applying_position:
            return
        key = UUID(identifier)
        previous = self._last_layout_positions.get(identifier, (float(x), float(y)))
        delta_x, delta_y = float(x) - previous[0], float(y) - previous[1]
        self._last_layout_positions[identifier] = (float(x), float(y))
        self._workspace.diagram_positions[key] = (float(x), float(y))
        if abs(delta_x) > 1e-9 or abs(delta_y) > 1e-9:
            for label_key, model in self._label_models.items():
                if model.owner_id != key:
                    continue
                label_item = self._label_items.get(label_key)
                if label_item is not None:
                    label_item.moveBy(delta_x, delta_y)
                    label_item._emit_changed()
        self._update_branch_geometry()
        self.layout_changed.emit(identifier, float(x), float(y))

    def prepare_for_shutdown(self) -> None:
        """Disconnect scene callbacks before Qt starts destroying the canvas.

        QGraphicsScene can emit ``selectionChanged`` while its C++ destructor
        clears selected graphics items.  Calling back into that partially
        destroyed scene from Python is unsafe, so detach the slot while the
        scene is still valid.  This method is intentionally idempotent.
        """
        if not self._selection_callback_connected:
            return
        self._scene.selectionChanged.disconnect(self._emit_selection)
        self._selection_callback_connected = False

    def _emit_selection(self) -> None:
        selected = self._scene.selectedItems()
        if not selected:
            self.element_selected.emit("", "")
            return
        item = selected[0]
        data = item.data(ROLE_ELEMENT)
        if isinstance(data, tuple) and len(data) == 2:
            self.element_selected.emit(str(data[0]), str(data[1]))

    def select_element(self, element_id: UUID) -> None:
        item = self._draft_symbol_items.get(str(element_id))
        if item is None:
            item = next(
                (
                    candidate
                    for candidate in self._scene.items()
                    if isinstance(candidate.data(ROLE_ELEMENT), tuple)
                    and candidate.data(ROLE_ELEMENT)[1] == str(element_id)
                ),
                None,
            )
        if item is None and self._workspace is not None:
            placement = next(
                (
                    item
                    for item in self._workspace.diagram_symbols.values()
                    if item.equipment_id == element_id
                ),
                None,
            )
            if placement is not None:
                item = self._draft_symbol_items.get(str(placement.instance_id))
        if item is not None:
            self._scene.clearSelection()
            item.setSelected(True)
            self.centerOn(item)

    def selected_element_refs(self) -> tuple[tuple[str, str], ...]:
        """Return selected editable objects as stable (kind, UUID) references."""
        allowed = {"bus", "equipment", "generator", "line", "diagram_symbol", "label"}
        result: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for item in self._scene.selectedItems():
            data = item.data(ROLE_ELEMENT)
            if not isinstance(data, tuple) or len(data) != 2:
                continue
            kind, identifier = str(data[0]), str(data[1])
            reference = (kind, identifier)
            if kind in allowed and reference not in seen:
                seen.add(reference)
                result.append(reference)
        return tuple(result)

    def selected_movable_positions(self) -> tuple[tuple[str, float, float], ...]:
        """Return selected domain/drawing objects that support positional nudging."""
        allowed = {"bus", "equipment", "generator", "line", "diagram_symbol"}
        result: list[tuple[str, float, float]] = []
        seen: set[str] = set()
        for item in self._scene.selectedItems():
            data = item.data(ROLE_ELEMENT)
            if not isinstance(data, tuple) or len(data) != 2:
                continue
            kind, identifier = str(data[0]), str(data[1])
            if kind not in allowed or identifier in seen:
                continue
            if not item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable:
                continue
            position = item.pos()
            result.append((identifier, float(position.x()), float(position.y())))
            seen.add(identifier)
        return tuple(result)

    def select_all_elements(self) -> None:
        """Select visible electrical and drawing objects, excluding editable text labels."""
        allowed = {"bus", "equipment", "generator", "line", "diagram_symbol"}
        self._scene.clearSelection()
        for item in self._scene.items():
            data = item.data(ROLE_ELEMENT)
            if not item.isVisible() or not isinstance(data, tuple) or len(data) != 2:
                continue
            if str(data[0]) in allowed and item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable:
                item.setSelected(True)
        self.viewport().update()

    def clear_selection(self) -> None:
        self._scene.clearSelection()
        self.viewport().update()

    @property
    def selected_bus_ids(self) -> tuple[UUID, ...]:
        """Return currently selected bus IDs; graphics selection never changes topology."""
        selected_ids: list[UUID] = []
        for item in self._scene.selectedItems():
            if isinstance(item, BusSymbol):
                selected_ids.append(item.identifier)
        return tuple(selected_ids)

    @property
    def grid_visible(self) -> bool:
        return self._grid_visible

    def set_grid_visible(self, visible: bool) -> None:
        self._grid_visible = bool(visible)
        self.viewport().update()

    def set_snap_enabled(self, enabled: bool) -> None:
        self._snap_enabled = bool(enabled)
        if self._workspace is not None:
            self._grid_spacing = float(self._workspace.grid_spacing)
            self._workspace.snap_enabled = self._snap_enabled
        for item in self._bus_items.values():
            item.snap = self._snap_enabled
            item.grid_spacing = self._grid_spacing
        for collection in (self._source_items, self._equipment_items, self._branch_items):
            for item in collection.values():
                item.snap_enabled = self._snap_enabled
                item.grid_spacing = self._grid_spacing
        for item in self._draft_symbol_items.values():
            item.snap_enabled = self._snap_enabled
            item.grid_spacing = self._grid_spacing
        self.viewport().update()

    def apply_position(self, identifier: str, x: float, y: float) -> None:
        item = (
            self._bus_items.get(identifier)
            or self._source_items.get(identifier)
            or self._equipment_items.get(identifier)
            or self._branch_items.get(identifier)
            or self._draft_symbol_items.get(identifier)
        )
        if item is None:
            return
        self._applying_position = True
        try:
            item.setPos(QPointF(x, y))
            actual = item.pos()
            actual_x, actual_y = float(actual.x()), float(actual.y())
            self._last_layout_positions[identifier] = (actual_x, actual_y)
            if self._workspace is not None:
                key = UUID(identifier)
                if key in self._workspace.diagram_symbols:
                    self._workspace.update_diagram_symbol(key, x=actual_x, y=actual_y)
                else:
                    self._workspace.diagram_positions[key] = (actual_x, actual_y)
            self._update_branch_geometry()
        finally:
            self._applying_position = False

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        super().drawBackground(painter, rect)
        if not self._grid_visible:
            return
        fine_grid = self._grid_spacing
        major_grid = fine_grid * 5.0
        left = math.floor(rect.left() / fine_grid) * fine_grid
        top = math.floor(rect.top() / fine_grid) * fine_grid
        fine_lines = []
        major_lines = []
        x = left
        while x < rect.right():
            target = major_lines if math.isclose(x % major_grid, 0.0, abs_tol=1e-7) else fine_lines
            target.append((QPointF(x, rect.top()), QPointF(x, rect.bottom())))
            x += fine_grid
        y = top
        while y < rect.bottom():
            target = major_lines if math.isclose(y % major_grid, 0.0, abs_tol=1e-7) else fine_lines
            target.append((QPointF(rect.left(), y), QPointF(rect.right(), y)))
            y += fine_grid
        painter.setPen(QPen(QColor("#F2F4F7"), 0.0))
        for start, end in fine_lines:
            painter.drawLine(start, end)
        painter.setPen(QPen(QColor("#E7EBF0"), 0.0))
        for start, end in major_lines:
            painter.drawLine(start, end)

    def wheelEvent(self, event) -> None:
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(factor, factor)

    def contextMenuEvent(self, event) -> None:
        item = self.itemAt(event.pos())
        if isinstance(item, QETSymbolItem) and item.instance_id is not None:
            item.setSelected(True)
            menu = QMenu(self)
            menu.addAction(
                "Rotate 90° clockwise",
                lambda: self.rotate_symbol_requested.emit(str(item.instance_id), 90.0),
            )
            menu.addAction(
                "Rotate 90° counterclockwise",
                lambda: self.rotate_symbol_requested.emit(str(item.instance_id), -90.0),
            )
            menu.addSeparator()
            menu.addAction("Remove drawing symbol", self.remove_symbol_requested.emit)
            menu.exec(event.globalPos())
            event.accept()
            return
        super().contextMenuEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton):
            self.setFocus(Qt.FocusReason.MouseFocusReason)
        if event.button() is Qt.MouseButton.MiddleButton:
            self._middle_pan = True
            self._pan_last = event.position().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._middle_pan and self._pan_last is not None:
            current = event.position().toPoint()
            delta = current - self._pan_last
            self._pan_last = current
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._middle_pan and event.button() is Qt.MouseButton.MiddleButton:
            self._middle_pan = False
            self._pan_last = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._position_empty_state()
