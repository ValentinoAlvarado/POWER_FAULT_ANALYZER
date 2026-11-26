# APP-REBOOT-002.1 — Ruff gate repair

## Findings from Windows verification

The first QET importer gate reported 34 Ruff findings. They were not all caused by the QET importer:

- The stateful research notebook had cross-cell duplicate imports, cell-local import ordering and a display-expression warning. The notebook is an interactive research artifact, not application source; it is now explicitly excluded from Ruff discovery. It is not rewritten by this repair.
- Application-source findings were import ordering, three unused imports, a deprecated `typing.Iterable` import, one equivalent boolean-branch simplification, and the diagnostic tuple construction flagged as an unsafe autofix.
- New QET test files had import-block spacing and unnecessary `noqa` directives.

## Changes

- Corrected imports and removed only imports confirmed unused by Ruff.
- Replaced `tuple((*diagnostics, *sequence_diagnostics))` with tuple concatenation. Both operands are typed tuples, so the result remains a tuple; no unsafe autofix was used.
- Moved optional PySide6 imports in the rendering test into a helper after `pytest.importorskip`, preserving collection on environments without desktop extras.
- Explicitly excluded only `POWER_FAULT_ANALYZER.ipynb` from Ruff. `ruff check .` still discovers and checks source, tests, and scripts.
- Scoped the PowerShell quality gate to `src`, `tests`, and `scripts`, matching the maintained code boundary.

## Verification performed in build environment

- `python -m compileall -q src tests scripts`: PASS
- `python -m pytest -q`: 552 passed, 2 skipped (PySide6 unavailable in this build container)
- Ruff 0.17.6 could not be executed in this container because it is not installed and package-index DNS is unavailable. Windows must re-run the repository gate to certify lint and format.

## No changes

No electrical solver, study parameters, sequence-network calculations, QET asset bytes, pinned Git blob hashes, or symbol-catalog entries were changed.
