# APP-REBOOT-001 — Build and verification report

## Snapshot and branch

- Baseline snapshot: `PRODUCT_FAULT_ANALYZER_APP-001_BASELINE_SNAPSHOT.zip` (APP-001 code and prior Windows gate fixes; original Git history was not present in the ZIP).
- Baseline tag in reconstructed build repository: `app-001-verified-baseline`.
- Product branch: `product-reboot`.
- Baseline commit: recorded in `BUILD-METADATA.json`.
- Increment commit: recorded in `BUILD-METADATA.json`.

The Git repository was reconstructed from the delivered source snapshot because the user's source ZIP did not contain `.git`. The original local Git commit history therefore cannot be represented or claimed as preserved. The electrical source files, tests, ND-014/015/016 documentation and validation data are retained in the baseline snapshot.

## Implemented desktop scope

- Dockable Qt workbench with menus and modelling/analysis toolbars.
- Project Explorer, Equipment Palette, Properties Inspector and Calculation Console.
- Qt Graphics View network canvas with grid, snap, zoom, middle-button pan and rubber-band selection.
- Physical AC bus, explicit Thevenin source, synchronous generator and series-line construction workflows.
- Physical `Network` aggregate remains separate from diagram-coordinate metadata.
- Network topology validation and explicit rejection of series lines across incompatible nominal voltage levels (no implicit transformer insertion).
- Project metadata and physical-network sidecar persistence, including historical numerical result snapshots.
- Background fault-study execution using `QThreadPool` / `QRunnable`; solver cancellation is not advertised because the solver contract has no cancellation facility.
- Phase and sequence result workspaces and current-phasor plotting.
- Existing PDF/XLSX/CSV/JSON report-export use case and adapter.
- REF-3PH-001 template materialized from the existing ND-016 reference dataset; the smoke test invokes the actual network sequence builder and production short-circuit solver.

## Explicit exclusions

Transformers, motors, loads, shunts, breakers, disconnectors, CTs, VTs and protection devices are not insertable via the desktop in this increment. The Properties Inspector is read-only. Diagram-position undo/redo is provided; physical-topology undo/redo, clipboard, automatic layout, layer management, direct terminal-drag connections, and historical report re-export are not implemented. See the engineering design document for full limitations.

## Verification in this build container

- Python: 3.13.5.
- `python -m pytest -q`: **542 passed**.
- `python -m compileall -q src tests scripts`: PASS.
- ND-016 CLI rerun: internal analytical benchmark 4/4, 44/44 quantities, electrical audits 4/4, sensitivity PASS (`4.4807532073381883e-07`), global external comparison `not_performed`.
- Ruff: not run in this container (Ruff executable/module is not installed here).
- PySide6 interactive/offscreen smoke test: not run in this container (PySide6 is not installed here). A Windows PowerShell verifier is supplied to run Ruff, Compileall, Pytest and the offscreen PySide6 end-to-end smoke test in the user's environment.

The user's preceding Windows run confirms APP-001 passed Ruff lint, Ruff format (281 files), Compileall, 535 tests and Qt window construction. APP-REBOOT-001 introduces additional tests; the current container collected and passed 542 tests. The new Windows verifier must be run on the reboot patch before claiming that its full Qt smoke test passed in Windows.

## ND-016 and REF-3PH-001B

This increment does not close ND-016. The individual REF-3PH-001B comparison remains 6/6 PASS based on high-precision values transcribed by the user from PowerWorld Simulator 24 Generator and Bus Records and phase-normalized before comparison. Native `.pwb`, original CSV exports and PowerWorld Message Log are still absent. REF-SLG-001, REF-LL-001 and REF-DLG-001 external comparisons remain pending.

## Apply on Windows

1. Create or switch to the `product-reboot` branch before applying the patch. If the local repository does not have Git metadata, initialize it and commit the verified APP-001 tree first; do not commit the APP-REBOOT patch as the baseline.
2. Extract the incremental ZIP at the repository root.
3. Run `scripts/start_product_reboot.ps1` to create/switch to the branch and tag the pre-increment HEAD when needed.
4. Run `scripts/verify_app_reboot_001.ps1` (or `-SkipInstall` after installing `.[dev,desktop,reports]`).
5. Launch `python -m power_fault_analyzer.interfaces.desktop.app`.
