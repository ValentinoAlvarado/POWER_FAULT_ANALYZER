"""Export the three canonical PFA engineering figure scenarios.

Run from the repository root with its virtual environment active:
    python scripts/export_pfa_design_003_reference_scenarios.py
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

from examples.canonical_model_scenarios import (  # noqa: E402
    build_double_bus_substation,
    build_multibus_network,
    build_single_bus_substation,
)
from power_fault_analyzer.diagram.model_document_export import (  # noqa: E402
    export_engineering_pdf,
    export_engineering_png,
    export_engineering_svg,
)
from power_fault_analyzer.diagram.model_projection import (  # noqa: E402
    project_network_to_diagram,
    validate_diagram_document,
)


SCENARIOS = (
    ("01_single_bus", build_single_bus_substation),
    ("02_double_bus", build_double_bus_substation),
    ("03_multibus", build_multibus_network),
)
INCREMENT = "PFA-DESIGN-003.6"
PRESET = "double-column"
OUTPUT = ROOT / "outputs" / "pfa_design_003_6_preview"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, object] = {
        "product": "POWER_FAULT_ANALYZER",
        "increment": INCREMENT,
        "source": "canonical Network / NetworkWorkspace",
        "preset": PRESET,
        "page_size_mm": [180.0, 120.0],
        "scenarios": [],
    }
    for name, builder in SCENARIOS:
        workspace = builder()
        document = project_network_to_diagram(workspace)
        diagnostics = validate_diagram_document(workspace, document)
        if diagnostics:
            raise RuntimeError(f"{name}: diagram validation failed: {diagnostics}")
        files = {
            "svg": export_engineering_svg(
                document, OUTPUT / f"{name}.svg", preset=PRESET,
                title=f"{name.replace('_', ' ').title()} — {INCREMENT}",
            ),
            "pdf": export_engineering_pdf(
                document, OUTPUT / f"{name}.pdf", preset=PRESET,
                title=f"{name.replace('_', ' ').title()} — {INCREMENT}",
            ),
            "png": export_engineering_png(
                document, OUTPUT / f"{name}.png", preset=PRESET,
                title=f"{name.replace('_', ' ').title()} — {INCREMENT}",
                output_width_px=2400,
            ),
        }
        manifest["scenarios"].append({
            "id": name,
            "network_id": str(document.network_id),
            "bus_count": len(document.buses),
            "equipment_count": len(document.symbols),
            "terminal_count": len(document.terminal_ids),
            "canonical_connection_count": len(document.connection_pairs),
            "diagnostics": list(diagnostics),
            "files": {kind: {"name": path.name, "sha256": sha256(path)}
                      for kind, path in files.items()},
        })
        print(f"PASS {name}: {len(document.buses)} buses, {len(document.symbols)} devices, "
              f"{len(document.terminal_ids)} terminals; SVG/PDF/PNG")
    manifest_path = OUTPUT / "SCENARIO_MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
