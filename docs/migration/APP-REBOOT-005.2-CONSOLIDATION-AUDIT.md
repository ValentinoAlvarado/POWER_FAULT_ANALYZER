# APP-REBOOT-005.2 — consolidation and closure audit

**Reference date:** 2026-11-23  
**Source branch:** `product-reboot`  
**Source commit:** `d0639ad7c96d8cd162e5a44950a81e18efcf46bd`

## Scope and repository identity

The recovery source consists of a complete working-tree ZIP plus a Git Bundle. The Bundle preserves the committed QET/product-reboot history (10 commits, from `dfef8a649ddd36ce6b2a5a697ba405ba58fbb99d` through `d0639ad7c96d8cd162e5a44950a81e18efcf46bd`). The ZIP additionally contains the uncommitted worktree state recorded at snapshot time: 12 modified tracked files and 39 new files. The source commit `1632134` is not present in this history; the rotation/persistence work is present as worktree content in the ZIP, not as that commit.

The destination's last known Windows state is clean `product-reboot` at `2523e598f624301ce4dd36770869678bde5c4acb`, with a single root commit. The destination and QET Bundle histories have no common ancestor. Consolidation therefore needs an explicit merge commit preserving both histories, followed by a snapshot-import commit that records the ZIP's working-tree changes.

## Tree comparison

The comparison was made against the previously supplied destination source snapshot and the current QET working-tree ZIP. Text files were compared after newline normalization; binary assets were compared byte-for-byte.

| Measure | Count |
|---|---:|
| Destination snapshot files | 362 |
| QET working-tree ZIP files | 438 |
| Common paths | 357 |
| Identical common paths | 349 |
| Different common paths | 8 |
| QET-only project paths | 80 |
| QET snapshot metadata file (not project source) | 1 |
| Destination-only paths to preserve | 5 |

The eight shared-path differences, for which the QET working-tree snapshot is the newer source of truth, are:

- `POWER_FAULT_ANALYZER.ipynb`
- `README.md`
- `pyproject.toml`
- `src/power_fault_analyzer.egg-info/SOURCES.txt`
- `src/power_fault_analyzer.egg-info/entry_points.txt`
- `src/power_fault_analyzer/application/use_cases/project_workspace.py`
- `src/power_fault_analyzer/interfaces/desktop/app.py`
- `src/power_fault_analyzer/results/report_builder.py.nd015-ruff-backup`

The five destination-only paths must remain untouched:

- `_REPOSITORY_SNAPSHOT_METADATA.txt`
- `src/power_fault_analyzer/validation/external_reference.py.nd016-ruff-cli-backup`
- `src/power_fault_analyzer/validation/sensitivity.py.nd016-ruff-cli-backup`
- `tests/unit/standards/iec60909/test_current_strategies.py.nd014-final-backup`
- `tests/unit/validation/test_nd016_validation.py.nd016-ruff-cli-backup`

`SNAPSHOT_METADATA.txt` is provenance generated for the handoff and contains a local Windows path. It is preserved with the source handoff/backups, but is not copied into the product repository. A sanitized provenance summary is maintained in this document.

## APP-REBOOT-005.2 finalization changes prepared

1. `scripts/build_windows_release.ps1` now invokes `verify_app_reboot_005.ps1` instead of the obsolete APP-REBOOT-004 verifier. The selected Python 3.13 interpreter is also used to invoke PyInstaller.
2. `JSONNetworkDocumentRepository` now writes schema `1.1` and reads both `1.0` and `1.1`. Legacy `1.0` documents without `diagram.symbols` remain valid; symbol instances and rotations are read when present; missing `rotation_deg` defaults to `0.0`.
3. Persistence tests cover schema `1.1` round-trip, legacy `1.0` documents with and without symbol arrays, legacy symbol rotation, and rejection of unsupported schema versions.
4. The APP-REBOOT-005 GUI smoke test now exercises actual symbol dragging, movement commit, undo/redo of position, rotation, selection preservation, hide/show, removal/restore, and JSON position/rotation persistence.
5. The APP-REBOOT-005 and QET verification scripts use the selected Python interpreter consistently and compile `src`, `tests`, and `scripts`.

No short-circuit solver, electrical equation, numerical tolerance, benchmark reference, or electrical domain contract was changed by these finalization edits.

## Reproduced checks in the available build environment

Environment: Python 3.13.5.

| Check | Result |
|---|---|
| `python -m pytest -q` | 558 passed, 4 skipped |
| `python -m compileall -q src tests scripts` | PASS |
| ND-016 analytical validation | 4/4 cases; 44/44 quantities PASS |
| Electrical audits | 4/4 cases PASS |
| Sensitivity refinement | PASS; relative derivative difference `4.481e-07` |
| Independent external-tool comparison | NOT PERFORMED |
| Ruff lint / format | NOT RUN; Ruff unavailable in this environment |
| PySide6 GUI smoke | NOT RUN; PySide6 unavailable in this environment |
| Clean Windows portable package | NOT BUILT; release intentionally remains blocked by empty `LICENSE` and pending legal review |

The four skipped tests require PySide6. The GUI smoke script is prepared, but movement, rendering and the full APP-REBOOT-005 acceptance remain pending execution on the user's Windows/PySide6 environment.

## Remaining limitations and safeguards

- `LICENSE` remains empty. No project license is selected or created by this work.
- `website/index.html` still contains a repository-owner placeholder; the site is not ready to publish.
- The JSON network-document adapter currently serializes equivalent sources, synchronous generators and lines. Transformers and other equipment are not yet covered by the persistence contract.
- QElectroTech files remain drawing candidates with separate attribution/license terms. Their presence in `EN 60617` collections does not establish IEC 60617 conformity or authorization to redistribute the IEC database.
- The PowerWorld external comparison remains `NOT_PERFORMED`; historical 6/6 figures are not elevated to a reproducible external validation claim.
- The migration script backs up both folders and original handoff artifacts, preserves both Git histories, overlays the source snapshot without deleting destination-only files, runs the Windows release acceptance gates, and removes the temporary QET folder only if every required gate succeeds and the final working tree is clean. If a check fails, the temporary QET folder is retained.

## APP-REBOOT-006 entry condition

Do not start APP-REBOOT-006 until the local consolidation has completed and the APP-REBOOT-005 Windows gates have passed. APP-REBOOT-006 should formalize `DiagramDocument` and explicit symbol-to-engineering-object/terminal mappings. Drawing proximity or line crossings must never create electrical connectivity implicitly.
