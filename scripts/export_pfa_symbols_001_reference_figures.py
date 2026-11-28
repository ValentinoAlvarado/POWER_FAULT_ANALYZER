"""Export canonical PFA diagrams after PFA-SYMBOLS-001.

Run from the repository root with the desktop/report dependencies installed.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for import_root in (ROOT, ROOT / "src"):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from examples.canonical_model_scenarios import (  # noqa: I001
    build_double_bus_substation,
    build_multibus_network,
    build_single_bus_substation,
)
from power_fault_analyzer.diagram.model_document_export import (
    export_engineering_pdf,
    export_engineering_png,
    export_engineering_svg,
)
from power_fault_analyzer.diagram.model_projection import (
    project_network_to_diagram,
    validate_diagram_document,
)


SCENARIOS = (
    ("01_single_bus", build_single_bus_substation),
    ("02_double_bus", build_double_bus_substation),
    ("03_multibus", build_multibus_network),
)
OUTPUT = ROOT / "outputs" / "current" / "symbols"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, object] = {
        "product": "POWER_FAULT_ANALYZER",
        "increment": "PFA-SYMBOLS-001",
        "symbol": "PFA-SLD-TRANSFORMER-2W-001",
        "symbol_reference": "IEC 60617 S00841 Form 1",
        "normative_status": "NOT_VERIFIED",
        "renderer": "canonical DiagramDocument -> shared symbol catalog -> SVG/PDF/PNG",
        "scenarios": [],
    }
    for name, builder in SCENARIOS:
        workspace = builder()
        document = project_network_to_diagram(workspace)
        diagnostics = validate_diagram_document(workspace, document)
        if diagnostics:
            raise RuntimeError(f"{name}: projection diagnostics: {diagnostics}")
        files = {
            "svg": export_engineering_svg(
                document, OUTPUT / f"{name}.svg", preset="double-column",
                title=f"{name.replace('_', ' ').title()} — PFA-SYMBOLS-001",
            ),
            "pdf": export_engineering_pdf(
                document, OUTPUT / f"{name}.pdf", preset="double-column",
                title=f"{name.replace('_', ' ').title()} — PFA-SYMBOLS-001",
            ),
            "png": export_engineering_png(
                document, OUTPUT / f"{name}.png", preset="double-column",
                title=f"{name.replace('_', ' ').title()} — PFA-SYMBOLS-001",
                output_width_px=2400,
            ),
        }
        manifest["scenarios"].append({
            "id": name,
            "network_id": str(document.network_id),
            "buses": len(document.buses),
            "equipment": len(document.symbols),
            "terminals": len(document.terminal_ids),
            "connections": len(document.connection_pairs),
            "diagnostics": list(diagnostics),
            "files": {
                kind: {"name": path.name, "sha256": _sha256(path)}
                for kind, path in files.items()
            },
        })
        print(f"PASS {name}: SVG/PDF/PNG, topology diagnostics=0")

    manifest_path = OUTPUT / "SYMBOL_SCENARIO_MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
