# QElectroTech symbol importer — code increment

## What is implemented

This increment adds a source-pinned importer and a Qt renderer for QElectroTech `.elmt` element definitions.

- `infrastructure/symbols/qet_elmt.py` parses the source XML into immutable typed definitions.
- `infrastructure/symbols/qet_catalog.py` loads the curated CSV manifest, checks the source commit and CC BY 3.0 identifier, verifies each Git blob SHA-1, and checks the `ELEMENTS.LICENSE` notice.
- `interfaces/desktop/workbench/qet_symbol_item.py` renders supported source primitives directly using `QPainter`; it does not redraw an IEC-like substitute.
- `interfaces/desktop/workbench/qet_symbol_browser.py` browses and previews the acquired source collection in a dock.
- `WorkbenchWindow` exposes the browser as the **IEC Symbol Library** dock.

The importer retains the original XML bytes, raw primitive XML, source UUID, dimensions, hotspot, terminal UUIDs/coordinates/orientations, author/license notice, upstream repository/commit/path, Git blob SHA-1, SHA-256 and normative status.

## What is deliberately not implemented yet

- A QET symbol is not automatically an electrical equipment object.
- Previewing a symbol does not create a bus, generator, transformer, breaker or load.
- Terminal-to-domain binding is not inferred from terminal order or graphical coincidence.
- No imported asset is labelled IEC 60617:2026 verified solely because it belongs to QElectroTech's `91_en_60617` collection.
- Unsupported source primitives are preserved and reported; they are not replaced with hand-drawn graphics.
- This increment does not yet replace the legacy bus/source glyph classes in `network_canvas.py`. That replacement requires a validated symbol-to-domain mapping and must be a subsequent increment. The new browser is a source-backed library/preview, not a false claim that the whole canvas is already normative.

## Acquire source assets on Windows

Run from the repository root in Windows PowerShell 5.1:

```powershell
.\scripts\Acquire-QElectroTechSymbolSeed.ps1
```

The downloader uses the pinned upstream commit in the CSV manifest and verifies the Git blob SHA-1 of every downloaded source file. It also downloads and preserves the upstream `ELEMENTS.LICENSE` notice and writes a SHA-256 inventory.

The raw source assets are placed under:

```text
assets/third_party/qelectrotech-elements/
```

The raw symbol collection is not included in this code patch. It is obtained from the public upstream repository by the acquisition script.

## Run verification

```powershell
.\scripts\verify_qet_symbol_importer.ps1
```

The verification script runs Ruff, format checks, compileall, the complete Pytest suite and a PySide6 offscreen import/render smoke test against the pinned synchronous-generator symbol.

## Geometry and connection semantics

The renderer applies the QET-declared hotspot translation to source primitive coordinates and uses the declared width/height as the item rectangle. It preserves the original hotspot and exposes `hotspot_position()` and `terminal_position(terminal_uuid)` in item-local coordinates. The mapping to PFA equipment terminals remains an explicit application/domain operation.

For a diagram instance to be connected, the caller must request `QETSymbolItem(..., require_connectable=True)` or call `SymbolDefinition.require_connectable()`. A source with no terminal definitions can still be previewed but cannot be used as a connectable symbol.

## Licensing and normative status

The seed collection is identified as CC BY 3.0 by its own `ELEMENTS.LICENSE`; preserve the notice when redistributing the source collection. The QElectroTech application source is not imported or linked into PFA. Imported symbol candidates remain `candidate` until their exact normative reference, edition and intended diagram context are checked. The official IEC database is not bundled.
