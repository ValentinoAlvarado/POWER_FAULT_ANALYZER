"""PySide6 renderer for imported QElectroTech vector primitives.

This module is a presentation adapter only. It does not create electrical
network objects or infer terminal-to-domain mappings.
"""

from __future__ import annotations

from uuid import UUID

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QGraphicsItem, QGraphicsObject, QStyleOptionGraphicsItem, QWidget

from power_fault_analyzer.diagram.layout import Point, snap_point
from power_fault_analyzer.infrastructure.symbols.qet_elmt import (
    QETSymbolFormatError,
    SymbolDefinition,
    SymbolPrimitive,
)


class UnsupportedQETPrimitiveError(QETSymbolFormatError):
    """The source contains a visual primitive not yet supported by the renderer."""


class QETSymbolItem(QGraphicsObject):
    """Render an imported QET definition without redrawing its electrical glyph.

    Source coordinates are translated by the measured primitive bounds. The
    original hotspot remains in the definition and is not guessed or rewritten.
    Terminal positions use the same translation as the visible geometry.
    """

    position_committed = Signal(str, float, float, float, float)

    _SUPPORTED = frozenset({"line", "ellipse", "rect", "rectangle", "arc", "polygon", "text"})

    def __init__(
        self,
        definition: SymbolDefinition,
        *,
        display_name: str | None = None,
        parent: QGraphicsObject | None = None,
        require_connectable: bool = False,
        interactive: bool = False,
        instance_id: UUID | None = None,
        rotation_deg: float = 0.0,
        snap_enabled: bool = True,
        grid_spacing: float = 20.0,
    ) -> None:
        super().__init__(parent)
        if require_connectable:
            definition.require_connectable()
        unsupported = sorted(
            {
                item.kind
                for item in definition.primitives
                if item.kind not in self._SUPPORTED and item.kind not in {"dynamic_text", "input"}
            }
        )
        if unsupported:
            raise UnsupportedQETPrimitiveError(
                f"Cannot render {definition.display_name!r}; unsupported primitives: {', '.join(unsupported)}."
            )
        if interactive and not isinstance(instance_id, UUID):
            raise TypeError("Interactive QET drawing items require a placement UUID.")
        self.definition = definition
        self.display_name = display_name or definition.display_name
        self.instance_id = instance_id
        self.asset_id = definition.provenance.asset_id
        self._interactive = interactive
        self.snap_enabled = bool(snap_enabled)
        self.grid_spacing = float(grid_spacing)
        if not 2.0 <= self.grid_spacing <= 200.0:
            raise ValueError("grid_spacing must be between 2 and 200 scene units.")
        self._drag_start = QPointF()
        self._dragging = False
        # QET primitive coordinates are translated by the declared hotspot in
        # paint().  The clickable/paintable bounds must use that same translated
        # coordinate system.  A number of upstream elements have primitives
        # outside the nominal width/height rectangle; using only that rectangle
        # clips the source artwork in previews and on the drawing canvas.
        nominal = QRectF(
            0.0,
            0.0,
            max(1.0, definition.source_width),
            max(1.0, definition.source_height),
        )
        source_bounds = definition.bounds
        geometry = QRectF(
            source_bounds.left + definition.hotspot.x,
            source_bounds.top + definition.hotspot.y,
            max(1.0, source_bounds.width),
            max(1.0, source_bounds.height),
        )
        self._rect = nominal.united(geometry)
        flags = QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
        if interactive:
            flags |= (
                QGraphicsItem.GraphicsItemFlag.ItemIsMovable
                | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
            )
            self.setData(0, ("diagram_symbol", str(instance_id)))
        self.setFlags(flags)
        self.setTransformOriginPoint(definition.hotspot.x, definition.hotspot.y)
        self.setRotation(float(rotation_deg) % 360.0)
        self.setToolTip(
            f"{self.display_name}\n"
            f"Source: {definition.provenance.repository}/{definition.provenance.source_path}\n"
            f"License: {definition.provenance.license_identifier}\n"
            f"Normative status: {definition.provenance.normative_status}"
        )

    def boundingRect(self) -> QRectF:
        # Allow room for line caps, selection outline and source text glyphs.
        padding = 7.0 if self._interactive else 3.0
        return self._rect.adjusted(-padding, -padding, padding, padding)

    def terminal_position(self, terminal_uuid: str) -> QPointF:
        terminal = self.definition.terminal(terminal_uuid)
        return QPointF(
            terminal.position.x + self.definition.hotspot.x,
            terminal.position.y + self.definition.hotspot.y,
        )

    def hotspot_position(self) -> QPointF:
        """Return the source hotspot in this item's local coordinate system."""
        return QPointF(self.definition.hotspot.x, self.definition.hotspot.y)

    def mousePressEvent(self, event) -> None:
        self._drag_start = self.pos()
        self._dragging = self._interactive
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        try:
            super().mouseReleaseEvent(event)
            if not self._interactive or self.instance_id is None:
                return
            current = self.pos()
            if (current - self._drag_start).manhattanLength() > 0.1:
                self.position_committed.emit(
                    str(self.instance_id),
                    self._drag_start.x(),
                    self._drag_start.y(),
                    current.x(),
                    current.y(),
                )
        finally:
            self._dragging = False

    def itemChange(self, change, value):
        if (
            self._interactive
            and self._dragging
            and self.snap_enabled
            and change is QGraphicsItem.GraphicsItemChange.ItemPositionChange
        ):
            spacing = self.grid_spacing
            hotspot = self.transformOriginPoint()
            anchor_x = value.x() + hotspot.x()
            anchor_y = value.y() + hotspot.y()
            snapped = snap_point(Point(anchor_x, anchor_y), spacing)
            return QPointF(snapped.x - hotspot.x(), snapped.y - hotspot.y())
        return super().itemChange(change, value)

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        del option, widget
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if self._interactive and self.isSelected():
            selection_pen = QPen(QColor("#2563EB"), 1.2, Qt.PenStyle.DashLine)
            painter.setPen(selection_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self._rect.adjusted(-5.0, -5.0, 5.0, 5.0))
        painter.translate(self.definition.hotspot.x, self.definition.hotspot.y)
        for primitive in self.definition.visual_primitives:
            self._paint_primitive(painter, primitive)
        painter.restore()

    def _paint_primitive(self, painter: QPainter, primitive: SymbolPrimitive) -> None:
        attributes = dict(primitive.attributes)
        style = _parse_style(attributes.get("style", ""))
        color = QColor(style.get("color", "black"))
        if not color.isValid():
            color = QColor("black")
        pen = QPen(color)
        pen.setWidthF(1.0)
        if style.get("line-style") in {"dash", "dashed"}:
            pen.setStyle(Qt.PenStyle.DashLine)
        elif style.get("line-style") in {"dot", "dotted"}:
            pen.setStyle(Qt.PenStyle.DotLine)
        painter.setPen(pen)

        filling = style.get("filling", "none")
        if filling == "none":
            painter.setBrush(Qt.BrushStyle.NoBrush)
        else:
            fill_color = QColor(filling)
            painter.setBrush(fill_color if fill_color.isValid() else color)

        kind = primitive.kind
        if kind == "line":
            painter.drawLine(
                QPointF(primitive.number("x1"), primitive.number("y1")),
                QPointF(primitive.number("x2"), primitive.number("y2")),
            )
        elif kind == "ellipse":
            painter.drawEllipse(_rect_from(primitive))
        elif kind in {"rect", "rectangle"}:
            painter.drawRect(_rect_from(primitive))
        elif kind == "arc":
            rectangle = _rect_from(primitive)
            start = round(primitive.number("start", 0.0) * 16)
            span = round(primitive.number("angle", 0.0) * 16)
            painter.drawArc(rectangle, start, span)
        elif kind == "polygon":
            polygon = _polygon_from(primitive)
            if len(polygon) >= 2:
                painter.drawPolygon(QPolygonF(polygon))
        elif kind == "text":
            self._paint_text(painter, primitive)
        else:  # pragma: no cover - guarded by constructor
            raise UnsupportedQETPrimitiveError(f"Unsupported QET primitive {kind!r}.")

    @staticmethod
    def _paint_text(painter: QPainter, primitive: SymbolPrimitive) -> None:
        font_string = primitive.get("font", "") or ""
        font = QFont()
        if not font_string or not font.fromString(font_string):
            font = QFont("Segoe UI", 9)
        painter.setFont(font)
        color = QColor(primitive.get("color", "black") or "black")
        painter.setPen(QPen(color if color.isValid() else QColor("black")))
        x = primitive.number("x")
        y = primitive.number("y")
        rotation = primitive.number("rotation", 0.0)
        painter.save()
        if rotation:
            painter.translate(x, y)
            painter.rotate(rotation)
            painter.drawText(QPointF(0.0, 0.0), primitive.get("text", "") or "")
        else:
            painter.drawText(QPointF(x, y), primitive.get("text", "") or "")
        painter.restore()


def _rect_from(primitive: SymbolPrimitive) -> QRectF:
    return QRectF(
        primitive.number("x"),
        primitive.number("y"),
        primitive.number("width"),
        primitive.number("height"),
    )


def _polygon_from(primitive: SymbolPrimitive) -> list[QPointF]:
    attributes = dict(primitive.attributes)
    indexes = sorted(
        int(key[1:]) for key in attributes if key.startswith("x") and key[1:].isdigit()
    )
    points: list[QPointF] = []
    for index in indexes:
        y_key = f"y{index}"
        if y_key not in attributes:
            raise QETSymbolFormatError(f"Polygon primitive is missing {y_key!r}.")
        points.append(QPointF(float(attributes[f"x{index}"]), float(attributes[y_key])))
    return points


def _parse_style(raw_style: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for entry in raw_style.split(";"):
        if ":" not in entry:
            continue
        key, value = entry.split(":", 1)
        result[key.strip()] = value.strip()
    return result
