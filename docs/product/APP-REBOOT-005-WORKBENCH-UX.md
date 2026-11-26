# APP-REBOOT-005 — Workbench Visual Re-composition

**Date:** 2026-11-23  
**Base:** APP-REBOOT-004 (`fe660f7`)  
**Scope:** Desktop workspace composition, QET source preview, first-run canvas state and Qt binding compatibility.

## Rejection findings addressed

The APP-REBOOT-004 screenshot showed that a vertical stack of equipment, properties and source library panels forced the QET preview into a shallow viewport. It also left a visually empty grid when no network existed and exposed long text-heavy commands in the primary toolbar.

The Windows verification log contained a PySide6 compatibility failure: `QGraphicsItem.flags()` returned a `GraphicsItemFlag`, not a `QFlags` object exposing `testFlag()`.

## Changes

- Replaced the stacked right-hand panels with a three-tab inspector: Equipment, Properties and Source Library. The full inspector column remains horizontally resizable using the main workspace splitter. This gives the vector library almost the full inspector height instead of compressing it beneath multiple stacked panels.
- Rebuilt the primary toolbar as one compact command bar with short labels, tooltips and grouped commands. Added a separate active `Export SVG` command; the prior toolbar exposed only the study-report export action, which was disabled before a study was run.
- Added a document-level diagram header with the active network name, model counts, base MVA, grid/snap toggles and Fit command.
- Added project-tree filtering and hierarchy search so projects with more equipment do not require scrolling through every category.
- Starts the desktop workbench maximized so the initial view uses the available drawing area; normal resizing remains enabled and layout state is persisted.
- Replaced the equipment palette's full-width button list with a compact two-column set of equipment actions.
- Added a first-run canvas state with direct actions to create the first AC bus or load the REF-3PH-001B reference case. It disappears when the network or drawing document contains an item.
- Added explicit diagram-document controls for grid visibility, snap-to-grid, and fit-to-extents; the toolbar exposes a functional SVG export command rather than a disabled study-report export before the first run.
- Reduced grid contrast and introduced major grid lines every 100 scene units.
- Reworked the QET browser so the vector preview receives nearly the full available inspector height. Source provenance and terminal metadata are collapsed by default and remain accessible.
- Fixed preview auto-fit to reset the previous view transform and fit the actual transformed item bounds.
- Corrected QET item bounding geometry to include original source primitives that extend beyond the nominal element rectangle. Original source geometry is not rewritten.
- Updated the PySide6 graphics-item flag test to use bitwise flag membership.
- Added an acceptance script covering inspector tabs, canvas first-run state, preview viewport height, candidate insertion, rotation, undo/redo and persistence.

## Architecture and claims

The QET catalog remains a source-library catalog of candidates. This increment does not assert IEC 60617 conformity, create electrical equipment mappings, or infer network connectivity from a drawing-only symbol. No solver behaviour is changed.

## Acceptance

Run on Windows with the project's Python 3.13 environment and QET seed acquired. Inspect at 1440×900 and at a wider 1600×1000 layout:

```powershell
ruff check src tests scripts
ruff format --check src tests scripts
python -m compileall -q src tests scripts
python -m pytest
python scripts/smoke_test_app_reboot_005.py
```

Or execute `scripts/verify_app_reboot_005.ps1` to include the pinned-symbol import and renderer smoke check.

Manual visual acceptance still requires inspecting the application at a minimum of 1440×900 and verifying that the Source Library tab displays complete, uncropped vector bounds.
