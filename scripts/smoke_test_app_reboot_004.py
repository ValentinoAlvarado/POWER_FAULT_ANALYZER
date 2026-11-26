"""Offscreen acceptance smoke for the resizable SLD workbench and QET placements."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

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
    assert window.right_splitter.count() == 3, "Right workspace must expose three resizable panels."
    window.main_splitter.setSizes([270, 830, 460])
    window.right_splitter.setSizes([220, 190, 430])
    application.processEvents()
    assert all(size > 0 for size in window.main_splitter.sizes())
    assert all(size > 0 for size in window.right_splitter.sizes())
    assert window.main_splitter.handleWidth() >= 14
    assert window.right_splitter.handleWidth() >= 14
    assert window.main_splitter.handle(1).toolTip()
    assert window.right_splitter.handle(1).toolTip()
    assert window.main_splitter.handle(1).isVisible()
    assert window.right_splitter.handle(1).isVisible()
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
    selected = window.canvas.selected_diagram_symbol()
    assert selected is not None, "Newly inserted drawing symbol must be selected."
    instance_id, initial_rotation = selected
    assert initial_rotation == 90.0, "Placed symbol must inherit the preview orientation."
    assert instance_id in window.workspace.diagram_symbols
    assert len(window.canvas.source_candidate_items()) == 1
    window.canvas.set_source_candidate_visibility(False)
    assert not window.canvas.source_candidate_items()[0].isVisible()
    window.canvas.set_source_candidate_visibility(True)
    assert window.canvas.source_candidate_items()[0].isVisible()
    assert not window.workspace.network.equipment, (
        "Drawing placement must not mutate the electrical model."
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

    with tempfile.TemporaryDirectory(prefix="pfa-app-reboot-004-") as temporary:
        path = services.network_document_repository.save(
            window.workspace, Path(temporary) / "rotation-roundtrip.pfan"
        )
        loaded = services.network_document_repository.load(path)
        assert loaded.diagram_symbols[instance_id].rotation_deg == 180.0
        assert loaded.network.id == window.workspace.network.id

    window._dirty = False
    window.close()
    application.processEvents()
    print(
        "APP-REBOOT-004 PASS: resizable splitter layout, 18 source symbols, "
        "rotatable preview and drawing placement, snap-to-grid, undo/redo, "
        "remove/restore and JSON persistence."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
