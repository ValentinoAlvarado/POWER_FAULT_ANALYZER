from __future__ import annotations

import os
from uuid import uuid4

import pytest

from power_fault_analyzer.infrastructure.symbols.qet_elmt import (
    SymbolProvenance,
    git_blob_sha1,
    parse_qet_elmt,
)


def _qt_dependencies():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6.QtCore import QPointF, QRectF
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtWidgets import QApplication, QGraphicsItem, QGraphicsScene

    from power_fault_analyzer.interfaces.desktop.workbench.qet_symbol_item import (
        QETSymbolItem,
        UnsupportedQETPrimitiveError,
    )

    return (
        QPointF,
        QRectF,
        QImage,
        QPainter,
        QApplication,
        QGraphicsItem,
        QGraphicsScene,
        QETSymbolItem,
        UnsupportedQETPrimitiveError,
    )


def _application(application_type):
    instance = application_type.instance()
    return instance if instance is not None else application_type([])


def _definition():
    provenance = SymbolProvenance(
        repository="test/repository",
        source_commit="a" * 40,
        source_path="fixture/resistor.elmt",
        expected_git_blob_sha1=git_blob_sha1(XML),
        license_identifier="CC-BY-3.0",
    )
    return parse_qet_elmt(XML, provenance=provenance)


XML = b"""<definition version="0.100.0" type="element" width="20" height="20" hotspot_x="10" hotspot_y="10">
<uuid uuid="{11223344-5566-7788-99aa-bbccddeeff00}"/>
<names><name lang="en">Test resistor</name></names>
<informations>Author: Test
License: CC BY 3.0</informations>
<description>
<rect x="-10" y="-10" width="20" height="20" style="line-style:normal;line-weight:normal;filling:none;color:black"/>
<line x1="-10" y1="0" x2="-5" y2="0"/>
<terminal uuid="{01223344-5566-7788-99aa-bbccddeeff00}" name="A" x="-10" y="0" orientation="w" type="Generic"/>
</description></definition>"""


def test_qet_graphics_item_preserves_terminal_anchor_and_paints() -> None:
    (
        _,
        QRectF,
        QImage,
        QPainter,
        QApplication,
        _,
        QGraphicsScene,
        QETSymbolItem,
        _,
    ) = _qt_dependencies()
    _application(QApplication)
    definition = _definition()
    item = QETSymbolItem(definition, require_connectable=True)
    scene = QGraphicsScene()
    scene.addItem(item)
    assert item.terminal_position(definition.terminals[0].uuid).x() == 0.0
    assert item.terminal_position(definition.terminals[0].uuid).y() == 10.0
    assert item.hotspot_position().x() == 10.0
    assert item.hotspot_position().y() == 10.0

    image = QImage(320, 240, QImage.Format.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    scene.render(painter, QRectF(0, 0, 320, 240), item.boundingRect())
    painter.end()
    assert not image.isNull()


def test_interactive_qet_item_is_movable_and_rotatable_around_source_hotspot() -> None:
    QPointF, _, _, _, QApplication, QGraphicsItem, _, QETSymbolItem, _ = _qt_dependencies()
    _application(QApplication)
    definition = _definition()
    item = QETSymbolItem(definition, interactive=True, instance_id=uuid4(), rotation_deg=90.0)

    assert item.rotation() == pytest.approx(90.0)
    assert item.transformOriginPoint().x() == pytest.approx(definition.hotspot.x)
    assert item.transformOriginPoint().y() == pytest.approx(definition.hotspot.y)
    # PySide6 exposes QGraphicsItem.flags() as the combined enum value in
    # supported versions; bitwise membership is portable across bindings.
    assert item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable
    assert item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
    item.setPos(QPointF(13.0, 11.0))
    # Programmatic positioning is exact; grid snapping belongs to pointer drag.
    assert item.pos().x() == pytest.approx(13.0)
    assert item.pos().y() == pytest.approx(11.0)

    # Snap the declared hotspot (not an arbitrary top-left bounding-box corner).
    item._dragging = True  # mousePressEvent enables this during interactive movement
    item.setPos(QPointF(14.0, 13.0))
    item._dragging = False
    assert item.pos().x() == pytest.approx(10.0)
    assert item.pos().y() == pytest.approx(10.0)
    anchor = item.mapToScene(item.transformOriginPoint())
    assert anchor.x() == pytest.approx(20.0)
    assert anchor.y() == pytest.approx(20.0)


def test_qet_item_bounds_include_source_geometry_outside_nominal_rectangle() -> None:
    _, _, _, _, QApplication, _, _, QETSymbolItem, _ = _qt_dependencies()
    _application(QApplication)
    extended_xml = XML.replace(
        b'<line x1="-10" y1="0" x2="-5" y2="0"/>',
        b'<line x1="-30" y1="0" x2="-25" y2="0"/>',
    )
    provenance = SymbolProvenance(
        repository="test/repository",
        source_commit="a" * 40,
        source_path="fixture/extended.elmt",
        expected_git_blob_sha1=git_blob_sha1(extended_xml),
        license_identifier="CC-BY-3.0",
    )
    definition = parse_qet_elmt(extended_xml, provenance=provenance)
    item = QETSymbolItem(definition)

    assert item.boundingRect().left() <= -22.0


def test_qet_graphics_item_refuses_unsupported_primitive() -> None:
    (_, _, _, _, QApplication, _, _, QETSymbolItem, UnsupportedQETPrimitiveError) = (
        _qt_dependencies()
    )
    _application(QApplication)
    changed = XML.replace(b"<description>", b"<description><bezier x1='0' y1='0' />", 1)
    provenance = SymbolProvenance(
        repository="test/repository",
        source_commit="a" * 40,
        source_path="fixture/unsupported.elmt",
        expected_git_blob_sha1=git_blob_sha1(changed),
        license_identifier="CC-BY-3.0",
    )
    definition = parse_qet_elmt(changed, provenance=provenance)
    with pytest.raises(UnsupportedQETPrimitiveError, match="unsupported primitives"):
        QETSymbolItem(definition)
