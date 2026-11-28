from __future__ import annotations

import sys
from pathlib import Path

# Make repository-root helper packages (for example ``examples``) importable
# when this file is executed by path from any working directory.
_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

import argparse
import json
import os
from uuid import uuid4

from examples.canonical_model_scenarios import (
    build_double_bus_substation,
    build_multibus_network,
    build_single_bus_substation,
)
from power_fault_analyzer.application.use_cases.network_workspace import NetworkWorkspace
from power_fault_analyzer.application.use_cases.reference_network_template import (
    BuildReferenceNetworkTemplate,
)
from power_fault_analyzer.application.use_cases.substation_engineering import (
    BuildPFAES001Substation,
)
from power_fault_analyzer.diagram.model_document_export import (
    export_engineering_png,
    export_engineering_svg,
)
from power_fault_analyzer.diagram.model_projection import (
    project_network_to_diagram,
    validate_diagram_document,
)
from power_fault_analyzer.domain.aggregates.network import Network
from power_fault_analyzer.domain.entities.bus import Bus
from power_fault_analyzer.domain.entities.terminal import Terminal
from power_fault_analyzer.domain.enums.bus_kind import BusKind
from power_fault_analyzer.domain.enums.equipment_family import EquipmentFamily
from power_fault_analyzer.domain.value_objects.voltage import Voltage
from power_fault_analyzer.equipment.interfaces.unresolved_equipment import EngineeringParameter
from power_fault_analyzer.equipment.interfaces.unresolved_single_terminal import (
    UnresolvedSingleTerminalEquipment,
)


def build_load_compensation_workspace() -> NetworkWorkspace:
    network = Network("Load and reactive-compensation symbol gallery")
    voltage = Voltage.from_kv(13.8)
    bus = Bus("BUS-LOADS", voltage, kind=BusKind.BUSBAR)
    network.add_bus(bus)
    definitions = (
        ("LOAD-01", "static_load", EquipmentFamily.LOAD),
        ("CAP-BANK-01", "capacitor_bank", EquipmentFamily.COMPENSATION),
        ("REACTOR-01", "shunt_reactor", EquipmentFamily.COMPENSATION),
        ("SVC-01", "svc", EquipmentFamily.COMPENSATION),
    )
    for name, kind, family in definitions:
        identifier = uuid4()
        terminal = Terminal(identifier, "HV", voltage)
        # This is a visual-only acceptance fixture. Do not fabricate any
        # nameplate values: unresolved data must remain explicitly unresolved.
        parameters = (
            EngineeringParameter("rated_power_mw", "MW"),
            EngineeringParameter("power_factor", "pu"),
        ) if family is EquipmentFamily.LOAD else (
            EngineeringParameter("rated_power_mvar", "MVAr"),
        )
        equipment = UnresolvedSingleTerminalEquipment(
            id=identifier, name=name, terminal=terminal, equipment_kind=kind,
            family=family, parameters=parameters,
        )
        network.add_equipment(equipment)
        network.connect(terminal.id, bus.id)
    return NetworkWorkspace(network=network)


def _page_size(document) -> tuple[float, float]:
    xs = [item.bounds.x for item in document.buses] + [item.center.x for item in document.symbols]
    ys = [item.bounds.y for item in document.buses] + [item.center.y for item in document.symbols]
    width = max(xs) - min(xs) if xs else 1.0
    height = max(ys) - min(ys) if ys else 1.0
    return (420.0, 297.0) if width >= height else (297.0, 420.0)


def _render_qt(workspace: NetworkWorkspace, output: Path) -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtGui import QFontInfo, QFontMetricsF, QImage, QPainter
    from PySide6.QtWidgets import QApplication

    from power_fault_analyzer.interfaces.desktop.workbench.network_canvas import (
        NetworkCanvasView,
        _installed_scene_font_families,
    )

    app = QApplication.instance() or QApplication([])
    installed_fonts = _installed_scene_font_families()
    view = NetworkCanvasView()
    view.resize(1800, 1200)
    view.set_workspace(workspace)
    font_samples = []
    for label_item in view._label_items.values():
        font = label_item.font()
        metrics = QFontMetricsF(font)
        font_samples.append({
            "family": font.family(),
            "resolved_family": QFontInfo(font).family(),
            "pixel_size": font.pixelSize(),
            "latin_coverage": all(metrics.inFont(char) for char in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-"),
            "text": label_item.toPlainText()[:48],
        })
    unique_samples = {
        (item["family"], item["resolved_family"], item["pixel_size"], item["latin_coverage"])
        for item in font_samples
    }
    diagnostics = {
        "installed_families": list(installed_fonts),
        "samples": [dict(zip(
            ("family", "resolved_family", "pixel_size", "latin_coverage"), item
        )) for item in sorted(unique_samples)],
        "label_count": len(font_samples),
        "sample_text": [item["text"] for item in font_samples[:5]],
    }
    print(
        "PFA_QT_FONT_DIAGNOSTICS|"
        + json.dumps(diagnostics, ensure_ascii=False, separators=(",", ":")),
        flush=True,
    )
    invalid_samples = [
        item for item in font_samples
        if not item["resolved_family"] or not item["latin_coverage"]
    ]
    if invalid_samples:
        raise RuntimeError(
            "Qt acceptance gallery has labels without a resolved Latin-capable font: "
            + json.dumps(diagnostics, ensure_ascii=False, separators=(",", ":"))
        )
    view.show()
    app.processEvents()
    scene_rect = view.scene().sceneRect()
    view.fitInView(scene_rect, Qt.AspectRatioMode.KeepAspectRatio)
    app.processEvents()
    image = QImage(1800, 1200, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(0xFFFFFFFF)
    painter = QPainter(image)
    view.viewport().render(painter, QPoint())
    painter.end()
    if image.isNull() or not image.save(str(output), "PNG"):
        raise RuntimeError(f"Qt review image could not be written: {output}")
    view.close()
    view.deleteLater()
    app.processEvents()


def main() -> int:
    parser = argparse.ArgumentParser(description="Render the PFA diagram acceptance gallery.")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    pfa_es001 = BuildPFAES001Substation().execute()
    cases = (
        ("ref-3ph-001b", BuildReferenceNetworkTemplate().execute().workspace),
        ("pfa-es-001", pfa_es001.workspace),
        ("double-bus", build_double_bus_substation()),
        ("multi-bus", build_multibus_network()),
        ("mixed-resolved-pending", build_single_bus_substation()),
        ("loads-and-compensation", build_load_compensation_workspace()),
    )
    manifest = {"commit": os.environ.get("GITHUB_SHA", "local"), "cases": []}
    for name, workspace in cases:
        case_dir = output_dir / name
        case_dir.mkdir(parents=True, exist_ok=True)
        document = project_network_to_diagram(workspace)
        validation_errors = validate_diagram_document(workspace, document)
        if validation_errors:
            raise RuntimeError(f"{name}: diagram integrity failed: {validation_errors}")
        width_mm, height_mm = _page_size(document)
        svg_path = export_engineering_svg(
            document, case_dir / f"{name}.svg", width_mm=width_mm, height_mm=height_mm,
        )
        png_path = export_engineering_png(
            document, case_dir / f"{name}-svg.png", output_width_px=2400,
            width_mm=width_mm, height_mm=height_mm,
        )
        qt_path = case_dir / f"{name}-qt.png"
        _render_qt(workspace, qt_path)
        manifest["cases"].append({
            "name": name,
            "buses": len(document.buses),
            "busbars": sum(item.kind == "busbar" for item in document.buses),
            "connection_nodes": sum(item.kind == "connection_node" for item in document.buses),
            "equipment": len(document.symbols),
            "terminals": len(document.terminal_ids),
            "connections": len(document.conductors),
            "families": {family: sum(item.family == family for item in document.symbols)
                         for family in sorted({item.family for item in document.symbols})},
            "unresolved": sum(item.state == "unresolved" for item in document.symbols),
            "partial_data": sum(item.state == "partial-data" for item in document.symbols),
            "warnings": list(document.diagnostics),
            "validation_errors": list(validation_errors),
            "svg": str(svg_path.relative_to(output_dir)),
            "svg_png": str(png_path.relative_to(output_dir)),
            "qt_png": str(qt_path.relative_to(output_dir)),
        })
    manifest_path = output_dir / "gallery-manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"Rendered {len(manifest['cases'])} diagram cases to {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
