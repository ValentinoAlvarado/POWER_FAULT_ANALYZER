from __future__ import annotations

import os
from uuid import uuid4

import pytest


def _qt_dependencies():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtWidgets import QApplication, QGraphicsScene

    from power_fault_analyzer.diagram.layout import Point
    from power_fault_analyzer.diagram.model_projection import (
        LABEL_SCENE_UNITS_PER_PT,
        EngineeringLabel,
    )
    from power_fault_analyzer.interfaces.desktop.workbench.network_canvas import (
        CanonicalEquipmentSymbol,
        DiagramLabelItem,
    )

    return (
        QImage,
        QPainter,
        QApplication,
        QGraphicsScene,
        Point,
        EngineeringLabel,
        LABEL_SCENE_UNITS_PER_PT,
        CanonicalEquipmentSymbol,
        DiagramLabelItem,
    )


def _application(application_type):
    instance = application_type.instance()
    return instance if instance is not None else application_type([])


def test_engineering_label_font_is_scaled_in_diagram_scene_units():
    (
        _, _, QApplication, _, Point, EngineeringLabel, scene_scale, _, DiagramLabelItem,
    ) = _qt_dependencies()
    _application(QApplication)

    label = EngineeringLabel(
        owner_id=None,
        text="BUS-13K8-A",
        position=Point(100.0, 100.0),
        label_id=uuid4(),
        size_pt=7.5,
    )
    item = DiagramLabelItem(label)

    assert item.font().pixelSize() == round(label.size_pt * scene_scale)
    assert item.document().documentMargin() == pytest.approx(0.0)


def test_switch_symbol_bounds_include_scaled_function_marks():
    (
        _, _, QApplication, _, _, _, scene_scale, CanonicalEquipmentSymbol, _,
    ) = _qt_dependencies()
    _application(QApplication)

    cases = (
        ("circuit_breaker", 3.2 * scene_scale),
        ("disconnector", 4.5 * scene_scale),
        ("earthing_switch", 11.0 * scene_scale),
    )
    for index, (family, extension) in enumerate(cases):
        symbol = CanonicalEquipmentSymbol(
            uuid4(), f"TEST-{index}", family, "open", 44.0, 32.0,
        )
        bounds = symbol.boundingRect()
        nominal_right = 44.0 / 2.0
        assert bounds.right() >= nominal_right + extension - 1e-9


def test_canonical_qt_symbols_render_to_an_offscreen_scene_without_clipping():
    (
        QImage, QPainter, QApplication, QGraphicsScene, _, _, _,
        CanonicalEquipmentSymbol, _,
    ) = _qt_dependencies()
    _application(QApplication)

    scene = QGraphicsScene()
    families = (
        "circuit_breaker", "disconnector", "earthing_switch", "generic",
        "load", "capacitor", "reactor", "compensation",
    )
    for index, family in enumerate(families):
        item = CanonicalEquipmentSymbol(
            uuid4(), f"TEST-{family}", family, "open", 44.0, 32.0,
        )
        item.setPos(index * 100.0, 0.0)
        scene.addItem(item)

    image = QImage(520, 180, QImage.Format.Format_ARGB32)
    image.fill(0xFFFFFFFF)
    painter = QPainter(image)
    scene.render(painter)
    painter.end()

    assert not image.isNull()
    assert not scene.itemsBoundingRect().isEmpty()


def test_unresolved_load_and_compensation_symbols_render_with_visible_badges():
    (
        QImage, QPainter, QApplication, QGraphicsScene, _, _, _,
        CanonicalEquipmentSymbol, _,
    ) = _qt_dependencies()
    _application(QApplication)
    scene = QGraphicsScene()
    families = ("load", "capacitor", "reactor", "compensation")
    for index, family in enumerate(families):
        item = CanonicalEquipmentSymbol(
            uuid4(), f"{family}-pending", family, "unresolved", 52.0, 64.0,
        )
        item.setPos(index * 150.0, 0.0)
        scene.addItem(item)
        assert item.boundingRect().right() >= 26.0 + 24.0
        assert item.boundingRect().top() <= -32.0 - 24.0
    image = QImage(720, 220, QImage.Format.Format_ARGB32)
    image.fill(0xFFFFFFFF)
    painter = QPainter(image)
    scene.render(painter)
    painter.end()
    assert not image.isNull()
    assert not scene.itemsBoundingRect().isEmpty()


def test_unresolved_line_branch_keeps_state_badge_inside_qt_geometry():
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtWidgets import QApplication, QGraphicsScene

    from power_fault_analyzer.interfaces.desktop.workbench.network_canvas import BranchSymbol

    _application(QApplication)
    scene = QGraphicsScene()
    branch = BranchSymbol(
        uuid4(), "LINE-PENDING", QPointF(0.0, -80.0), QPointF(0.0, 80.0),
        "", state="unresolved",
    )
    assert branch.boundingRect().left() <= -29.0
    assert branch.boundingRect().right() >= 0.0
    scene.addItem(branch)
    image = QImage(240, 240, QImage.Format.Format_ARGB32)
    image.fill(0xFFFFFFFF)
    painter = QPainter(image)
    scene.render(painter)
    painter.end()
    assert not image.isNull()
