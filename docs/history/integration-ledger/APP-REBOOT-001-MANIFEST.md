# APP-REBOOT-001 — Incremental package manifest

## Package

`POWER_FAULT_ANALYZER_APP-REBOOT-001_ENGINEERING_WORKBENCH_20261123.zip`

## Git baseline

- Branch: `product-reboot`
- Baseline tag: `app-001-verified-baseline`
- Baseline commit: `dfef8a649ddd36ce6b2a5a697ba405ba58fbb99d`
- Implementation commit before packaging metadata: `d6caeef503cfc4e1250ffc5199c5b42f4db53c22`
- Original user ZIP did not include `.git`; the branch and tag were reconstructed from the delivered APP-001 snapshot. This does not preserve the user's original Git history.

## Increment scope

- Dockable PySide6 engineering workbench.
- Project explorer, equipment palette, properties inspector and calculation console.
- Qt Graphics View network canvas with physical network model separate from drawing coordinates.
- Functional creation workflows for AC bus, Thevenin equivalent source, synchronous generator and series transmission line.
- Network topology validation and explicit same-voltage-level rule for series lines.
- JSON persistence for project/network layout and historical numerical result snapshots.
- Asynchronous network short-circuit studies through the existing production `ShortCircuitSolver`.
- Phase and sequence results, phase-current phasor plot and existing engineering report exporters.
- REF-3PH-001 template sourced from the existing ND-016 dataset.

## Changed project paths

The archive preserves paths relative to the repository root. Files are enumerated in `SHA256SUMS.txt` in the package.

## Verified in build container

- Python 3.13.5
- Pytest: 542 passed
- Compileall: passed
- ND-016 internal analytical validation: 4/4 cases, 44/44 quantities, 4/4 audits, sensitivity passed
- ND-016 aggregate external state: `not_performed`
- Ruff: not executed here (not installed)
- PySide6 runtime smoke: not executed here (not installed)

The user's prior Windows evidence confirms the earlier APP-001 shell passed Ruff lint/format, Compileall, 535 tests and Qt window construction. This new workbench must still pass `scripts/verify_app_reboot_001.ps1` on Windows, including its offscreen Qt end-to-end smoke test.

## Explicit functional boundaries

Insertable in this increment: AC buses, Thevenin equivalent sources, synchronous generators, series transmission lines. Transformers, motors, loads, shunts, breakers, disconnectors, CTs, VTs and protection devices are not insertable through this UI increment. The properties inspector is read-only. Undo/redo covers diagram positions only. No claim of full editor parity with commercial packages is made.

## ND-016 provenance

REF-3PH-001B remains an individual 6/6 passing comparison against high-precision values transcribed by the user from PowerWorld Simulator 24 Generator and Bus Records and normalized into the PFA phase reference. Native PWB/CSV/Message Log provenance remains pending. REF-SLG-001, REF-LL-001 and REF-DLG-001 external comparisons remain pending.
