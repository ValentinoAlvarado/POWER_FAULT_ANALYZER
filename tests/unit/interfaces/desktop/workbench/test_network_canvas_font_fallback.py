from __future__ import annotations

import os
from uuid import uuid4

import pytest


def _qt_dependencies():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")

    from PySide6.QtGui import QFontDatabase, QRawFont
    from PySide6.QtWidgets import QApplication

    from power_fault_analyzer.diagram.layout import Point
    from power_fault_analyzer.diagram.model_projection import EngineeringLabel
    from power_fault_analyzer.interfaces.desktop.workbench.network_canvas import (
        DiagramLabelItem,
        _resolve_scene_font_family,
        _scene_font,
    )

    return (
        QApplication,
        QFontDatabase,
        QRawFont,
        Point,
        EngineeringLabel,
        DiagramLabelItem,
        _resolve_scene_font_family,
        _scene_font,
    )


def _ensure_application(application_type):
    instance = application_type.instance()
    return instance if instance is not None else application_type([])


def test_missing_preferred_font_uses_installed_segoe_ui_before_arial():
    (
        _, _, _, _, _, _, resolve_font_family, _,
    ) = _qt_dependencies()

    resolved = resolve_font_family(
        "STIX Two Text",
        available_families=["Arial", "Segoe UI"],
    )

    assert resolved == "Segoe UI"


def test_installed_requested_font_is_preserved():
    (
        _, _, _, _, _, _, resolve_font_family, _,
    ) = _qt_dependencies()

    resolved = resolve_font_family(
        "Cambria",
        available_families=["Segoe UI", "Cambria", "Arial"],
    )

    assert resolved == "Cambria"


def test_scene_font_uses_a_real_family_with_required_latin_glyphs():
    (
        QApplication,
        QFontDatabase,
        QRawFont,
        _,
        _,
        _,
        resolve_font_family,
        scene_font,
    ) = _qt_dependencies()
    _ensure_application(QApplication)

    resolved_family = resolve_font_family("STIX Two Text")
    installed = {
        family.partition(" [")[0].casefold()
        for family in QFontDatabase.families()
    }
    assert resolved_family.casefold() in installed

    raw_font = QRawFont.fromFont(scene_font("STIX Two Text", 9.0))
    assert raw_font.isValid()

    required_characters = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789.-+() /"
    unsupported = [
        character
        for character in required_characters
        if not raw_font.supportsCharacter(ord(character))
    ]
    assert unsupported == [], f"Font {resolved_family!r} lacks glyphs: {unsupported!r}"


def test_diagram_label_item_stores_the_resolved_font_family():
    (
        QApplication,
        _,
        _,
        Point,
        EngineeringLabel,
        DiagramLabelItem,
        resolve_font_family,
        _,
    ) = _qt_dependencies()
    _ensure_application(QApplication)

    label = EngineeringLabel(
        owner_id=None,
        text="BUS-13K8-A 13.8 kV",
        position=Point(100.0, 100.0),
        label_id=uuid4(),
        font_family="STIX Two Text",
        size_pt=9.0,
    )
    item = DiagramLabelItem(label)

    assert item.font_family == resolve_font_family("STIX Two Text")
    assert item.font().family() == item.font_family
