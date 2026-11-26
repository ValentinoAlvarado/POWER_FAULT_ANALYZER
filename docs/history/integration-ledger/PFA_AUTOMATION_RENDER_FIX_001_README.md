# PFA Automation + Rendering Fix 001

This patch is based on the uploaded POWER_FAULT_ANALYZER source snapshot.

## Included

- Fix `SourceSymbol.boundingRect()` so the generator name is included in the
  Qt item's paint bounds. The previous bounds covered only the circular glyph
  while the name was painted outside them, allowing Qt to clip/repaint the text
  incorrectly during updates.
- Counter-rotate busbar annotations in the paint routine so names and voltage
  labels remain upright when the busbar is rotated.
- Add `power_fault_analyzer.scripting.ScriptProject`, a first public Python API
  for creating real buses and explicit three-sequence equivalent sources in
  the existing domain model.
- Add an executable 60 kV sample and unit tests.

## Apply

Extract this archive into the repository root and allow overwrite of the
included source files. It contains only files listed in `PATCH_MANIFEST.txt`.

Then run:

```powershell
.\.venv\Scripts\python.exe -m ruff check src tests
.\.venv\Scripts\python.exe -m ruff format --check src tests
.\.venv\Scripts\python.exe -m compileall -q src tests examples
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe examples\automation\substation_60kv.py
```

## Verification performed in the build environment

- Unit tests: 577 passed, 4 skipped.
- Compileall: passed.
- Example script: passed with `PYTHONPATH=src` (the user's editable install
  should make the package importable without that override).
- Qt desktop rendering was not executed in this build environment because
  PySide6 is not installed here. The Qt visual fix must still be checked in the
  user's Windows desktop environment.

## Explicit scope boundary

This is not the full Code & Automation Studio. It supplies a real, tested first
slice of the public Python authoring API, but does not yet include an embedded
IDE, arbitrary script execution inside the Workbench, complete equipment
coverage, a headless vector renderer, or SVG/PDF export from scripts. Those
must not be represented as completed by this patch.
