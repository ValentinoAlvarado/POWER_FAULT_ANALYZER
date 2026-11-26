from __future__ import annotations

import csv
from pathlib import Path

import pytest

from power_fault_analyzer.infrastructure.symbols.qet_catalog import (
    QETSymbolCatalogError,
    load_qet_symbol_catalog,
)
from power_fault_analyzer.infrastructure.symbols.qet_elmt import git_blob_sha1

SYMBOL_XML = b"""<definition version="0.100.0" type="element" width="10" height="20" hotspot_x="5" hotspot_y="10">
<uuid uuid="{d64fdecb-7cad-cfe0-c390-1e173d880af5}"/>
<names><name lang="en">One winding</name><name lang="es">Un devanado</name></names>
<informations>Author: QET team
License: see elements license</informations>
<description><line x1="0" y1="0" x2="0" y2="10"/><terminal uuid="{6a719cbb-c86f-4a60-8a11-818aebb4363b}" name="" x="0" y="0" orientation="n" type="Generic"/></description>
</definition>"""


def _write_catalog(tmp_path: Path, *, expected_sha: str | None = None) -> tuple[Path, Path]:
    root = tmp_path / "assets"
    symbol_path = root / "fixture" / "one-winding.elmt"
    symbol_path.parent.mkdir(parents=True)
    symbol_path.write_bytes(SYMBOL_XML)
    (root / "ELEMENTS.LICENSE").write_text(
        "This work is licensed under the Creative Commons Attribution 3.0 License.",
        encoding="utf-8",
    )
    manifest = tmp_path / "qet-symbols.csv"
    row = {
        "asset_id": "QET-ONE-WINDING",
        "description_en": "One winding",
        "description_es": "Un devanado",
        "qet_path": "fixture/one-winding.elmt",
        "qet_git_blob_sha1": expected_sha or git_blob_sha1(SYMBOL_XML),
        "collection_commit": "661f5e9ce5caa76277cafd3ebf0e0320fc4af229",
        "source_license": "CC-BY-3.0",
        "normative_status": "candidate",
        "pfa_target_view": "multi-line",
        "notes": "Test fixture",
    }
    with manifest.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)
    return manifest, root


def test_catalog_loads_pinned_manifest_and_preserves_asset_identifier(tmp_path: Path) -> None:
    manifest, root = _write_catalog(tmp_path)
    catalog = load_qet_symbol_catalog(manifest, root)

    assert len(catalog.symbols) == 1
    symbol = catalog.by_asset_id("QET-ONE-WINDING")
    assert symbol.display_name == "Un devanado"
    assert symbol.provenance.asset_id == "QET-ONE-WINDING"
    assert symbol.provenance.normative_status == "candidate"


def test_catalog_rejects_symbol_blob_hash_mismatch(tmp_path: Path) -> None:
    manifest, root = _write_catalog(tmp_path, expected_sha="0" * 40)
    with pytest.raises(QETSymbolCatalogError, match="Git blob mismatch"):
        load_qet_symbol_catalog(manifest, root)


def test_catalog_rejects_unapproved_license_in_manifest(tmp_path: Path) -> None:
    manifest, root = _write_catalog(tmp_path)
    text = manifest.read_text(encoding="utf-8").replace("CC-BY-3.0", "UNLICENSED")
    manifest.write_text(text, encoding="utf-8")
    with pytest.raises(QETSymbolCatalogError, match="unapproved source license"):
        load_qet_symbol_catalog(manifest, root)


def test_catalog_rejects_path_traversal(tmp_path: Path) -> None:
    manifest, root = _write_catalog(tmp_path)
    text = manifest.read_text(encoding="utf-8").replace(
        "fixture/one-winding.elmt", "../outside.elmt"
    )
    manifest.write_text(text, encoding="utf-8")
    with pytest.raises(QETSymbolCatalogError, match="Unsafe QET asset path"):
        load_qet_symbol_catalog(manifest, root)
