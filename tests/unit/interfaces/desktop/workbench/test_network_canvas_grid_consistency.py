from __future__ import annotations

import os
from uuid import uuid4

import pytest


def _qt_dependencies():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6.QtCore import QPointF
    from PySide6.QtWidgets import QApplication

    from power_fault_analyzer.domain.enums.bus_kind import BusKind
    from power_fault_analyzer.interfaces.desktop.workbench.network_canvas import (
        BranchSymbol,
        BusSymbol,
        CanonicalEquipmentSymbol,
        SourceSymbol,
    )

    return QApplication, QPointF, BusKind, BranchSymbol, BusSymbol, CanonicalEquipmentSymbol, SourceSymbol


def _application(application_type):
    instance = application_type.instance()
    return instance if instance is not None else application_type([])


def _coordinates(item):
    return item.pos().x(), item.pos().y()


def test_programmatic_positions_are_not_quantized_when_snap_is_enabled():
    (
        QApplication,
        QPointF,
        BusKind,
        BranchSymbol,
        BusSymbol,
        CanonicalEquipmentSymbol,
        SourceSymbol,
    ) = _qt_dependencies()
    _application(QApplication)

    items = (
        BusSymbol(uuid4(), "BUS-1", 13.8, True, BusKind.BUSBAR, 200.0, grid_spacing=20.0),
        SourceSymbol(uuid4(), "GRID-1", "equivalent_source", snap_enabled=True, grid_spacing=20.0),
        CanonicalEquipmentSymbol(
            uuid4(), "CB-1", "circuit_breaker", "closed", 44.0, 28.0,
            snap_enabled=True, grid_spacing=20.0,
        ),
        BranchSymbol(
            uuid4(), "LINE-1", QPointF(-22.0, 0.0), QPointF(22.0, 0.0), "",
            snap_enabled=True, grid_spacing=20.0,
        ),
    )

    for item in items:
        item.setPos(QPointF(50.0, 70.0))
        assert _coordinates(item) == pytest.approx((50.0, 70.0))


def test_drag_positions_share_configured_grid_snap_policy():
    (
        QApplication,
        QPointF,
        BusKind,
        BranchSymbol,
        BusSymbol,
        CanonicalEquipmentSymbol,
        SourceSymbol,
    ) = _qt_dependencies()
    _application(QApplication)

    spacing = 10.0
    items = (
        BusSymbol(uuid4(), "BUS-1", 13.8, True, BusKind.BUSBAR, 200.0, grid_spacing=spacing),
        SourceSymbol(uuid4(), "GRID-1", "equivalent_source", snap_enabled=True, grid_spacing=spacing),
        CanonicalEquipmentSymbol(
            uuid4(), "CB-1", "circuit_breaker", "closed", 44.0, 28.0,
            snap_enabled=True, grid_spacing=spacing,
        ),
        BranchSymbol(
            uuid4(), "LINE-1", QPointF(-22.0, 0.0), QPointF(22.0, 0.0), "",
            snap_enabled=True, grid_spacing=spacing,
        ),
    )

    for item in items:
        item._dragging = True  # mousePressEvent enables this only for a real drag
        item.setPos(QPointF(25.0, 35.0))
        assert _coordinates(item) == pytest.approx((30.0, 40.0))
        item._dragging = False


def test_grid_spacing_is_shared_and_configurable_for_all_electrical_items():
    (
        QApplication,
        QPointF,
        BusKind,
        BranchSymbol,
        BusSymbol,
        CanonicalEquipmentSymbol,
        SourceSymbol,
    ) = _qt_dependencies()
    _application(QApplication)

    spacing = 10.0
    items = (
        BusSymbol(uuid4(), "BUS-1", 13.8, True, BusKind.BUSBAR, 200.0, grid_spacing=spacing),
        SourceSymbol(uuid4(), "GRID-1", "equivalent_source", snap_enabled=True, grid_spacing=spacing),
        CanonicalEquipmentSymbol(
            uuid4(), "CB-1", "circuit_breaker", "closed", 44.0, 28.0,
            snap_enabled=True, grid_spacing=spacing,
        ),
        BranchSymbol(
            uuid4(), "LINE-1", QPointF(-22.0, 0.0), QPointF(22.0, 0.0), "",
            snap_enabled=True, grid_spacing=spacing,
        ),
    )

    for item in items:
        item._dragging = True
        item.setPos(QPointF(25.0, 35.0))
        assert _coordinates(item) == pytest.approx((30.0, 40.0))
        item._dragging = False


def test_disabling_snap_makes_all_electrical_items_move_continuously():
    (
        QApplication,
        QPointF,
        BusKind,
        BranchSymbol,
        BusSymbol,
        CanonicalEquipmentSymbol,
        SourceSymbol,
    ) = _qt_dependencies()
    _application(QApplication)

    bus = BusSymbol(uuid4(), "BUS-1", 13.8, False, BusKind.BUSBAR, 200.0, grid_spacing=20.0)
    source = SourceSymbol(uuid4(), "GRID-1", "equivalent_source", snap_enabled=False, grid_spacing=20.0)
    equipment = CanonicalEquipmentSymbol(
        uuid4(), "CB-1", "circuit_breaker", "closed", 44.0, 28.0,
        snap_enabled=False, grid_spacing=20.0,
    )
    branch = BranchSymbol(
        uuid4(), "LINE-1", QPointF(-22.0, 0.0), QPointF(22.0, 0.0), "",
        snap_enabled=False, grid_spacing=20.0,
    )

    for item in (bus, source, equipment, branch):
        item._dragging = True
        item.setPos(QPointF(43.25, 67.75))
        assert _coordinates(item) == pytest.approx((43.25, 67.75))
        item._dragging = False
