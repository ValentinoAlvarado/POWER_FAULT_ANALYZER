"""Offscreen acceptance smoke for the resizable SLD workbench and QET placements."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QGraphicsItem

from power_fault_analyzer.bootstrap.workbench_container import build_workbench_services
from power_fault_analyzer.interfaces.desktop.workbench.workbench_window import WorkbenchWindow


def main() -> int:
    application = QApplication.instance() or QApplication([])
    services = build_workbench_services()
    window = WorkbenchWindow(services)
    window.resize(1600, 1000)
    window.show()
    application.processEvents()

    assert window.main_splitter.count() == 3, "Main workspace must expose three resizable columns."
    assert window.inspector_tabs.count() == 3, (
        "Inspector must expose equipment, properties and source tabs."
    )
    window.main_splitter.setSizes([270, 830, 460])
    application.processEvents()
    assert all(size > 0 for size in window.main_splitter.sizes())
    assert window.main_splitter.handleWidth() >= 8
    assert window.main_splitter.handle(1).toolTip()
    assert window.main_splitter.handle(1).isVisible()
    assert window.diagram_header.isVisible(), "The diagram must expose its own document controls."
    assert window.diagram_title.text() == window.workspace.network.name
    assert window.grid_toggle.isCheckable() and window.snap_toggle.isCheckable()
    window.grid_toggle.setChecked(False)
    assert not window.canvas.grid_visible
    window.grid_toggle.setChecked(True)
    assert window.canvas.grid_visible
    window.explorer_search.setText("network")
    application.processEvents()
    assert not window.explorer.topLevelItem(0).isHidden()
    window.explorer_search.clear()
    assert window.canvas._empty_state.isVisible(), "Empty networks must show a first-run guide."
    window.inspector_tabs.setCurrentWidget(window.symbol_browser_panel)
    application.processEvents()
    assert window.symbol_browser.preview.viewport().height() >= 220, (
        "Source preview must receive a useful viewport when its inspector tab is active."
    )
    window.symbol_browser._fit_preview()
    application.processEvents()
    preview_item = window.symbol_browser._preview_item
    assert preview_item is not None
    preview_bounds = preview_item.sceneBoundingRect()
    preview_scene = window.symbol_browser.preview_scene.sceneRect()
    assert preview_scene.contains(preview_bounds), (
        "Preview scene must contain the full source geometry, including primitives outside nominal bounds."
    )
    window._set_editing_enabled(False)
    assert not window.palette_panel.isEnabled()
    window._set_editing_enabled(True)
    assert window.palette_panel.isEnabled()

    catalog = window.symbol_browser.catalog
    assert catalog is not None, "Pinned QET source symbol catalog did not load."
    assert len(catalog.symbols) == 18, (
        f"Expected 18 pinned source symbols, got {len(catalog.symbols)}."
    )
    window.symbol_browser._rotate_preview(90.0)
    assert window.symbol_browser._preview_item is not None
    assert window.symbol_browser._preview_item.rotation() == 90.0
    window.symbol_browser._request_insert()
    assert window.show_source_candidates_action.isChecked(), (
        "Explicit source-symbol insertion must reveal the drawing-only candidate layer."
    )
    assert window.canvas._source_candidates_visible
    selected = window.canvas.selected_diagram_symbol()
    assert selected is not None, "Newly inserted drawing symbol must be selected."
    instance_id, initial_rotation = selected
    assert initial_rotation == 90.0, "Placed symbol must inherit the preview orientation."
    assert instance_id in window.workspace.diagram_symbols
    assert len(window.canvas.source_candidate_items()) == 1
    assert not window.canvas._empty_state.isVisible(), (
        "A placed drawing reference must dismiss the empty-canvas guide."
    )
    window.show_source_candidates_action.setChecked(False)
    assert not window.canvas.source_candidate_items()[0].isVisible()
    window.show_source_candidates_action.setChecked(True)
    assert window.canvas.source_candidate_items()[0].isVisible()
    restored_selection = window.canvas.selected_diagram_symbol()
    assert restored_selection is not None and restored_selection[0] == instance_id, (
        "Restoring the source layer must preserve the selected drawing symbol."
    )
    assert not window.workspace.network.equipment, (
        "Drawing placement must not mutate the electrical model."
    )
    placed_item = window.canvas.source_candidate_items()[0]
    assert placed_item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable, (
        "Inserted drawing candidates must be movable graphics items."
    )
    original_position = window.workspace.diagram_symbols[instance_id]
    drag_start = window.canvas.mapFromScene(placed_item.sceneBoundingRect().center())
    drag_end = drag_start + QPoint(48, 32)
    QTest.mousePress(window.canvas.viewport(), Qt.MouseButton.LeftButton, pos=drag_start)
    QTest.mouseMove(window.canvas.viewport(), drag_end, 40)
    QTest.mouseRelease(window.canvas.viewport(), Qt.MouseButton.LeftButton, pos=drag_end)
    application.processEvents()
    moved_placement = window.workspace.diagram_symbols[instance_id]
    assert (
        abs(moved_placement.x - original_position.x) + abs(moved_placement.y - original_position.y)
    ) > 0.1, "Dragging a drawing symbol did not commit a new position."
    moved_x, moved_y = moved_placement.x, moved_placement.y
    window._undo_stack.undo()
    restored_position = window.workspace.diagram_symbols[instance_id]
    assert (
        restored_position.x == original_position.x and restored_position.y == original_position.y
    ), "Undo did not restore the previous drawing position."
    window._undo_stack.redo()
    restored_position = window.workspace.diagram_symbols[instance_id]
    assert restored_position.x == moved_x and restored_position.y == moved_y, (
        "Redo did not restore the committed drawing position."
    )

    window._rotate_selected_symbol(90.0)
    placement = window.workspace.diagram_symbols[instance_id]
    assert placement.rotation_deg == 180.0, (
        "Clockwise rotation was not persisted in workspace state."
    )
    window._undo_stack.undo()
    assert window.workspace.diagram_symbols[instance_id].rotation_deg == 90.0
    window._undo_stack.redo()
    assert window.workspace.diagram_symbols[instance_id].rotation_deg == 180.0

    window._remove_selected()
    assert instance_id not in window.workspace.diagram_symbols
    window._undo_stack.undo()
    assert instance_id in window.workspace.diagram_symbols

    with tempfile.TemporaryDirectory(prefix="pfa-app-reboot-005-") as temporary:
        path = services.network_document_repository.save(
            window.workspace, Path(temporary) / "rotation-roundtrip.pfan"
        )
        loaded = services.network_document_repository.load(path)
        persisted_placement = loaded.diagram_symbols[instance_id]
        assert persisted_placement.rotation_deg == 180.0
        assert persisted_placement.x == moved_x and persisted_placement.y == moved_y
        assert loaded.network.id == window.workspace.network.id

    window._dirty = False
    window.close()
    application.processEvents()
    print(
        "APP-REBOOT-005 PASS: filtered project explorer, document-level diagram controls, "
        "compact command bar, tabbed inspector, first-run canvas, complete source preview, "
        "18 pinned assets, rotatable drawing placement, undo/redo, remove/restore "
        "and JSON persistence."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
