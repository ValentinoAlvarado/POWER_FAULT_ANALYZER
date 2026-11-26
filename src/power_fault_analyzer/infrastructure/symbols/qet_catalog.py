"""Pinned-manifest loader for the QElectroTech Elements seed collection."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from power_fault_analyzer.infrastructure.symbols.qet_elmt import (
    QETSymbolError,
    SymbolDefinition,
    SymbolProvenance,
    load_qet_elmt,
)


class QETSymbolCatalogError(QETSymbolError):
    """Raised when a symbol collection cannot be loaded with provenance intact."""


@dataclass(frozen=True, slots=True)
class QETSymbolCatalog:
    symbols: tuple[SymbolDefinition, ...]
    repository: str
    source_commit: str
    license_file: Path

    def by_asset_id(self, asset_id: str) -> SymbolDefinition:
        for symbol in self.symbols:
            if symbol.provenance.asset_id == asset_id:
                return symbol
        raise KeyError(f"No QET asset with source path/id {asset_id!r}.")


def load_qet_symbol_catalog(
    manifest_path: str | Path,
    asset_root: str | Path,
    *,
    locale: str = "es",
    expected_repository: str = "qelectrotech/qelectrotech-elements",
    expected_commit: str = "661f5e9ce5caa76277cafd3ebf0e0320fc4af229",
) -> QETSymbolCatalog:
    """Load every row in the pinned CSV manifest and verify each Git blob hash.

    The manifest is trusted configuration maintained with PFA. Symbol bytes are
    never trusted solely because their filename or folder resembles an IEC code.
    """

    manifest_file = Path(manifest_path).resolve()
    root = Path(asset_root).resolve()
    if not manifest_file.is_file():
        raise QETSymbolCatalogError(f"Symbol candidate manifest does not exist: {manifest_file}")
    license_file = root / "ELEMENTS.LICENSE"
    if not license_file.is_file():
        raise QETSymbolCatalogError(
            f"QElectroTech ELEMENTS.LICENSE is missing from the acquired asset root: {root}"
        )
    license_text = license_file.read_text(encoding="utf-8-sig")
    if "Creative Commons Attribution 3.0" not in license_text and "CC-BY" not in license_text:
        raise QETSymbolCatalogError(
            "QElectroTech license notice is missing or not recognized as CC BY 3.0."
        )

    repository = expected_repository
    commit = expected_commit
    loaded: list[SymbolDefinition] = []
    seen_asset_ids: set[str] = set()

    try:
        with manifest_file.open("r", encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream))
    except OSError as exc:
        raise QETSymbolCatalogError(f"Cannot read symbol manifest {manifest_file}: {exc}") from exc

    if not rows:
        raise QETSymbolCatalogError("QET symbol candidate manifest contains no assets.")

    for row_number, row in enumerate(rows, start=2):
        try:
            asset_id = _required(row, "asset_id")
            if asset_id in seen_asset_ids:
                raise QETSymbolCatalogError(
                    f"Duplicate asset_id {asset_id!r} at manifest row {row_number}."
                )
            seen_asset_ids.add(asset_id)

            row_commit = _required(row, "collection_commit")
            if row_commit != commit:
                raise QETSymbolCatalogError(
                    f"Manifest row {row_number} commit {row_commit!r} differs from pinned commit {commit!r}."
                )
            license_id = _required(row, "source_license")
            if license_id != "CC-BY-3.0":
                raise QETSymbolCatalogError(
                    f"Manifest row {row_number} has unapproved source license {license_id!r}."
                )

            relative_source = Path(_required(row, "qet_path"))
            if relative_source.is_absolute() or ".." in relative_source.parts:
                raise QETSymbolCatalogError(f"Unsafe QET asset path at manifest row {row_number}.")
            symbol_path = (root / relative_source).resolve()
            if root not in symbol_path.parents:
                raise QETSymbolCatalogError(
                    f"QET asset path escapes the asset root at row {row_number}."
                )

            provenance = SymbolProvenance(
                repository=repository,
                source_commit=commit,
                source_path=relative_source.as_posix(),
                expected_git_blob_sha1=_required(row, "qet_git_blob_sha1"),
                license_identifier=license_id,
                asset_id=asset_id,
                normative_status=_required(row, "normative_status"),
                normative_reference=_optional(row, "normative_reference"),
                normative_edition=_optional(row, "normative_edition"),
            )
            symbol = load_qet_elmt(symbol_path, provenance=provenance, locale=locale)
            # Keep the manifest's human-facing asset identifier as a stable alias.
            # It is intentionally not confused with the source symbol UUID.
            loaded.append(symbol)
        except (KeyError, QETSymbolError, OSError) as exc:
            raise QETSymbolCatalogError(
                f"Cannot load QET symbol manifest row {row_number}: {exc}"
            ) from exc

    return QETSymbolCatalog(
        symbols=tuple(loaded),
        repository=repository,
        source_commit=commit,
        license_file=license_file,
    )


def _required(row: dict[str, str], key: str) -> str:
    value = row.get(key, "").strip()
    if not value:
        raise QETSymbolCatalogError(f"Manifest field {key!r} is required.")
    return value


def _optional(row: dict[str, str], key: str) -> str | None:
    value = row.get(key, "").strip()
    return value or None
