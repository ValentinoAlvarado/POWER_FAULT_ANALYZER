"""Qt Graphics View canvas: rendering metadata is deliberately separate from topology."""

from __future__ import annotations

import math
from uuid import UUID

from PySide6.QtCore import QObject, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsItem,
    QGraphicsObject,
    QGraphicsEllipseItem,
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
from power_fault_analyzer.domain.enums.bus_kind import BusKind
from power_fault_analyzer.diagram.layout import Point, perpendicular_bay_route
from power_fault_analyzer.diagram.symbol_catalog import get_symbol_definition
from power_fault_analyzer.diagram.model_projection import (
    EngineeringLabel, DiagramProjectionError, project_network_to_diagram,
)
from power_fault_analyzer.equipment.sources.equivalent_source import EquivalentSource
from power_fault_analyzer.equipment.sources.synchronous_generator import SynchronousGenerator
from power_fault_analyzer.infrastructure.symbols.qet_elmt import SymbolDefinition
from power_fault_analyzer.interfaces.desktop.workbench.qet_symbol_item import QETSymbolItem

ROLE_ELEMENT = 0


class BusSymbol(QGraphicsObject):
    moved = Signal(str, float, float)
    move_committed = Signal(str, float, float, float, float)

    def __init__(
        self, identifier: UUID, name: str, nominal_kv: float, snap: bool, kind: BusKind,
        width: float = 600.0,
    ) -> None:
        super().__init__()
        self._initializing = True
        self.identifier = identifier
        self.name = name
        self.nominal_kv = nominal_kv
        self.snap = snap
        self.kind = kind
        self.width = float(width)
        self._drag_start = QPointF()
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
        ink = QColor("#B66B12" if selected else "#172033")
        if self.kind is BusKind.BUSBAR:
            painter.setPen(QPen(ink, 3.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.SquareCap))
            painter.drawLine(QPointF(-self.width / 2.0, 0.0), QPointF(self.width / 2.0, 0.0))
        else:
            painter.setPen(QPen(ink, 1.4))
            painter.setBrush(QBrush(QColor("#FFFFFF")))
            painter.drawEllipse(QRectF(-4.0, -4.0, 8.0, 8.0))

    def mousePressEvent(self, event) -> None:
        self._drag_start = self.pos()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
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

    def itemChange(self, change, value):
        if change is QGraphicsItem.GraphicsItemChange.ItemPositionChange and self.snap:
            grid = 20.0
            point = value
            return QPointF(round(point.x() / grid) * grid, round(point.y() / grid) * grid)
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
                 label_text: str | None = None) -> None:
        super().__init__()
        self._initializing = True
        self.identifier, self.name, self.family, self.state = identifier, name, family, state
        self.width, self.height = width, height
        self.orientation_deg = orientation_deg
        self._drag_start = QPointF()
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
        half_width = (
            abs(math.cos(angle)) * self.width / 2.0
            + abs(math.sin(angle)) * self.height / 2.0
            + 8.0
        )
        half_height = (
            abs(math.sin(angle)) * self.width / 2.0
            + abs(math.cos(angle)) * self.height / 2.0
            + 8.0
        )
        return QRectF(-half_width, -half_height, 2.0 * half_width, 2.0 * half_height)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        del option, widget
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        selected = self.isSelected()
        ink = QColor("#D97706" if selected else "#172033")
        painter.save()
        painter.rotate(self.orientation_deg)
        painter.setPen(QPen(ink, 1.8))
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
            left, right = -self.width/2, self.width/2
            painter.drawEllipse(QPointF(left, 0), 2.4, 2.4)
            painter.drawEllipse(QPointF(right, 0), 2.4, 2.4)
            if self.state == "closed":
                painter.drawLine(QPointF(left, 0), QPointF(right, 0))
            else:
                painter.drawLine(QPointF(left, 0), QPointF(2, -self.height*0.22))
            # IEC 60617 candidate function marks: cross for circuit-breaker,
            # transverse bar for disconnector. Catalogue remains NOT_VERIFIED.
            mark_y = -self.height * 0.43
            if self.family == "circuit_breaker":
                radius = 3.2
                painter.drawLine(QPointF(right-radius, mark_y-radius),
                                 QPointF(right+radius, mark_y+radius))
                painter.drawLine(QPointF(right-radius, mark_y+radius),
                                 QPointF(right+radius, mark_y-radius))
            elif self.family == "disconnector":
                painter.drawLine(QPointF(right-4.5, mark_y), QPointF(right+4.5, mark_y))
            elif self.family == "earthing_switch":
                ground_y = self.height * 0.28
                painter.drawLine(QPointF(right+7.0, -ground_y), QPointF(right+7.0, -ground_y/2))
                painter.drawLine(QPointF(right+2.0, -ground_y/2), QPointF(right+12.0, -ground_y/2))
                painter.drawLine(QPointF(right+4.0, 0), QPointF(right+10.0, 0))
        elif self.family in {"generator", "source"}:
            painter.drawEllipse(QRectF(-20, -20, 40, 40))
            glyph = "G" if self.family == "generator" else "~"
            painter.drawText(QRectF(-16, -15, 32, 30), Qt.AlignmentFlag.AlignCenter, glyph)
        else:
            painter.drawEllipse(QRectF(-18, -18, 36, 36))
        painter.restore()
    def mousePressEvent(self, event) -> None:
        self._drag_start = self.pos()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        super().mouseReleaseEvent(event)
        current = self.pos()
        if (current-self._drag_start).manhattanLength() > 0.1:
            self.move_committed.emit(str(self.identifier), self._drag_start.x(),
                self._drag_start.y(), current.x(), current.y())

    def itemChange(self, change, value):
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

    def __init__(self, identifier: UUID, name: str, subtype: str) -> None:
        super().__init__()
        self._initializing = True
        self.identifier = identifier
        self.name = name
        self.subtype = subtype
        self._drag_start = QPointF()
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
        painter.setPen(QPen(ink, 2.0))
        painter.setBrush(QBrush(QColor("#FFFFFF")))
        painter.drawEllipse(QRectF(-22.0, -22.0, 44.0, 44.0))
        painter.setPen(QPen(ink, 1.4))
        painter.setFont(QFont("Segoe UI", 14, QFont.Weight.DemiBold))
        glyph = "G" if self.subtype == "synchronous_generator" else "~"
        painter.drawText(QRectF(-17.0, -16.0, 34.0, 32.0), Qt.AlignmentFlag.AlignCenter, glyph)

    def mousePressEvent(self, event) -> None:
        self._drag_start = self.pos()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
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

    def itemChange(self, change, value):
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
        self.font_family = label.font_family
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
        font = QFont(self.font_family)
        font.setPointSizeF(self.size_pt)
        font.setWeight({
            "normal": QFont.Weight.Normal,
            "medium": QFont.Weight.Medium,
            "semibold": QFont.Weight.DemiBold,
            "bold": QFont.Weight.Bold,
        }[self.weight])
        self.setFont(font)

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
            for name in ("STIX Two Text", "Cambria", "Arial", "Times New Roman")
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
        self, identifier: UUID, name: str, from_point: QPointF, to_point: QPointF, label: str
    ) -> None:
        super().__init__()
        self._branch_signals = _BranchSymbolSignals()
        self._initializing = True
        self.identifier = identifier
        self.name = name
        self._drag_start = QPointF()
        self.setData(ROLE_ELEMENT, ("line", str(identifier)))
        self.setZValue(2)
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setPen(QPen(QColor("#172033"), 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.SquareCap))
        self.setBrush(Qt.BrushStyle.NoBrush)
        self.set_endpoints(from_point, to_point)
        self.label_item = QGraphicsSimpleTextItem(label)
        self.label_item.setBrush(QBrush(QColor("#0F172A")))
        self.label_item.setFont(QFont("Segoe UI", 8, QFont.Weight.DemiBold))
        self.label_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
        self.label_item.setZValue(5)
        self._initializing = False

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
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        super().mouseReleaseEvent(event)
        current = self.pos()
        if (current - self._drag_start).manhattanLength() > 0.1:
            self.move_committed.emit(
                str(self.identifier), self._drag_start.x(), self._drag_start.y(),
                current.x(), current.y(),
            )

    def itemChange(self, change, value):
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
            self._scene.setSceneRect(QRectF(-1200.0, -900.0, 2400.0, 1800.0))
            self._update_empty_state()
            return
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
            link.setPen(QPen(QColor("#334155"), 1.6, Qt.PenStyle.SolidLine))
            link.setZValue(3)
            self._scene.addItem(link)
            self._conductor_items[str(conductor.terminal_id)] = link

        for bus in network.buses:
            projected = next(item for item in document.buses if item.bus_id == bus.id)
            bar_length = max(projected.bounds.width, projected.bounds.height)
            item = BusSymbol(bus.id, bus.name, bus.nominal_voltage.value_kv,
                             self._snap_enabled, bus.kind, bar_length)
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
        for conductor in document.conductors:
            if not conductor.points:
                continue
            marker = QGraphicsEllipseItem(-2.8, -2.8, 5.6, 5.6)
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
                line = BranchSymbol(equipment.id, equipment.name, p1, p2, "")
                self._scene.addItem(line)
                self._branch_items[str(equipment.id)] = line
                self._last_layout_positions[str(equipment.id)] = (line.pos().x(), line.pos().y())
                line.moved.connect(self._on_layout_changed)
                line.move_committed.connect(self.position_committed.emit)
            elif projected.family == "source" and isinstance(equipment, (EquivalentSource, SynchronousGenerator)):
                symbol = SourceSymbol(equipment.id, equipment.name, "equivalent_source"
                                      if isinstance(equipment, EquivalentSource)
                                      else "synchronous_generator")
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
                symbol = CanonicalEquipmentSymbol(
                    equipment.id, equipment.name, projected.family, projected.state,
                    projected.width, projected.height, projected.orientation_deg,
                    projected_label,
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
        self._update_branch_geometry()
        items_rect = self._scene.itemsBoundingRect()
        self._scene.setSceneRect(items_rect.adjusted(-120, -100, 180, 120)
                                 if not items_rect.isEmpty()
                                 else QRectF(-1200.0, -900.0, 2400.0, 1800.0))
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
            snap_enabled=False,
            grid_spacing=self._workspace.grid_spacing if self._workspace is not None else 20.0,
        )
        item.setPos(QPointF(placement.x, placement.y))
        if placement.equipment_id is not None:
            item.setData(ROLE_ELEMENT, ("equipment", str(placement.equipment_id)))
        item.snap_enabled = self._snap_enabled
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
        """Route each terminal wire from its current bus tap to its equipment pin."""
        if self._workspace is None:
            return
        for terminal_id, (bus_id, equipment_id, local_x, local_y, angle_deg, tap_axis_offset) in self._terminal_route_specs.items():
            bus_item = self._bus_items.get(str(bus_id))
            link = self._conductor_items.get(terminal_id)
            if bus_item is None or link is None:
                continue
            equipment_item = (
                self._source_items.get(str(equipment_id))
                or self._equipment_items.get(str(equipment_id))
                or self._branch_items.get(str(equipment_id))
            )
            if equipment_item is not None:
                item_angle = (0.0 if isinstance(equipment_item, BranchSymbol)
                              else float(getattr(equipment_item, "orientation_deg", angle_deg)))
                angle = math.radians(item_angle)
                terminal_point = equipment_item.pos() + QPointF(
                    local_x * math.cos(angle) - local_y * math.sin(angle),
                    local_x * math.sin(angle) + local_y * math.cos(angle),
                )
            else:
                # Line branches are immutable two-terminal spans in the current
                # Workbench interaction model; their pin coordinates stay fixed.
                terminal_point = self._terminal_projected_points.get(terminal_id)
                if terminal_point is None:
                    continue
            bus_point = bus_item.connection_point(terminal_point, tap_axis_offset)
            junction = self._junction_items.get(terminal_id)
            if junction is not None:
                junction.setPos(bus_point)
            # Use the exact same pure geometry routine as SVG/PDF projection.
            # It collapses a collinear bay into one segment instead of retaining
            # redundant intermediate QPainterPath elements, and uses one
            # Manhattan-minimal orthogonal jog only when a bar is moved off-lane.
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
                link.setPath(path)
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
        for item in self._bus_items.values():
            item.snap = self._snap_enabled
        for item in self._draft_symbol_items.values():
            item.snap_enabled = self._snap_enabled
        if self._workspace is not None:
            self._workspace.snap_enabled = self._snap_enabled

    def apply_position(self, identifier: str, x: float, y: float) -> None:
        item = (
            self._bus_items.get(identifier)
            or self._source_items.get(identifier)
            or self._equipment_items.get(identifier)
            or self._draft_symbol_items.get(identifier)
        )
        if item is None:
            return
        self._applying_position = True
        try:
            item.setPos(QPointF(x, y))
            if self._workspace is not None:
                key = UUID(identifier)
                if key in self._workspace.diagram_symbols:
                    self._workspace.update_diagram_symbol(key, x=x, y=y)
                else:
                    self._workspace.diagram_positions[key] = (float(x), float(y))
            self._update_branch_geometry()
        finally:
            self._applying_position = False

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        super().drawBackground(painter, rect)
        if not self._grid_visible:
            return
        fine_grid = 20.0
        major_grid = 100.0
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
