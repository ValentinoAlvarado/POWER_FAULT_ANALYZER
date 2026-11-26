"""Regression coverage for Qt graphics-item signal ownership."""
from __future__ import annotations

from uuid import uuid4

import pytest

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


def _application() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_branch_symbol_initialization_and_motion_use_bound_qt_signals():
    app = _application()
    symbol_id = uuid4()
    branch = BranchSymbol(
        symbol_id,
        "LINE-REGRESSION",
        QPointF(10.0, 20.0),
        QPointF(110.0, 20.0),
        "LINE-REGRESSION",
    )

    moved_events: list[tuple[str, float, float]] = []
    committed_events: list[tuple[str, float, float, float, float]] = []
    branch.moved.connect(lambda *args: moved_events.append(args))
    branch.move_committed.connect(lambda *args: committed_events.append(args))

    original = branch.pos()
    branch.setPos(original + QPointF(5.0, 7.0))

    assert moved_events == [(str(symbol_id), original.x() + 5.0, original.y() + 7.0)]
    assert committed_events == []
    assert branch.moved is not None
    assert branch.move_committed is not None
    assert app is QApplication.instance()


def test_qgraphicsobject_symbols_initialize_and_emit_their_native_signals():
    app = _application()
    symbols = (
        BusSymbol(uuid4(), "BUS-REGRESSION", 13.8, False, BusKind.BUSBAR, 180.0),
        CanonicalEquipmentSymbol(
            uuid4(), "CB-REGRESSION", "circuit_breaker", "closed", 32.0, 24.0
        ),
        SourceSymbol(uuid4(), "GRID-REGRESSION", "equivalent_source"),
    )

    for symbol in symbols:
        events: list[tuple[str, float, float]] = []
        symbol.moved.connect(lambda *args, sink=events: sink.append(args))
        symbol.setPos(QPointF(37.0, 53.0))
        assert events == [(str(symbol.identifier), 37.0, 53.0)], type(symbol).__name__
        assert symbol._initializing is False

    assert app is QApplication.instance()
