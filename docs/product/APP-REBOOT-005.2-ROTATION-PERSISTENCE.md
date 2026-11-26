# APP-REBOOT-005.2 — Diagram selection and rotation persistence hotfix

Date: 2026-11-23
Base: APP-REBOOT-005 / APP-REBOOT-005.1 (QHBoxLayout import hotfix)

## Defect addressed

The APP-REBOOT-005 acceptance sequence hid and restored the QET source-candidate
layer before issuing a rotate command. Qt deselects a QGraphicsItem when it becomes
invisible. The restored symbol was therefore visible but no longer selected; the
rotate command correctly refused to act on a missing selection, and the persisted
rotation remained unchanged.

## Changes

1. Preserve selected drawing-instance IDs while the source-candidate layer is hidden.
2. Restore those selections when the layer becomes visible again.
3. Discard retained selection IDs when a drawing instance is removed.
4. Move rotation persistence to WorkbenchWindow/application orchestration. The
   NetworkCanvasView now changes only the graphics item's visual rotation and no
   longer mutates NetworkWorkspace directly.
5. Extend the APP-REBOOT-005 smoke acceptance to assert that selection survives a
   hide/show cycle before checking rotation, undo/redo and JSON persistence.
6. Retain the QHBoxLayout import required by APP-REBOOT-005 visual document header.

## Boundaries

This hotfix does not map QET drawing candidates to electrical assets or terminals.
It does not change network topology, the short-circuit solver, IEC 60909 calculations,
or QET source assets.

## Finalization and persistence compatibility

The finalization pass updates the network-document writer to schema `1.1` while
retaining read compatibility for schema `1.0` and `1.1`. A legacy `1.0` document
without `diagram.symbols` remains valid. If a `1.0` document does contain symbols,
its placements and rotation are read; a missing `rotation_deg` defaults to `0.0`.
New saves use `1.1`. This is separate from the project-container schema.

The current serializer still supports only `EquivalentSource`, `SynchronousGenerator`
and `Line` equipment records. Transformer, motor and other equipment persistence is
not claimed by this increment and remains a tracked limitation.

The release build script now invokes `verify_app_reboot_005.ps1` rather than the
obsolete APP-REBOOT-004 verifier. All verifier stages use the selected Python 3.13
interpreter. The GUI smoke includes insertion, hide/show selection retention,
interactive movement, rotation, undo/redo, removal/restoration and JSON round-trip.

## Verification performed in the available build environment

- Python 3.13.5 `python -m pytest -q`: **558 passed, 4 skipped**.
- `python -m compileall -q src tests scripts`: PASS.
- ND-016 analytical validation: 4/4 cases and 44/44 quantities PASS.
- Electrical audits: 4/4 PASS.
- Sensitivity refinement: PASS (`4.481e-07` relative derivative difference).
- Ruff lint/format: NOT RUN because Ruff is unavailable in this environment.
- PySide6 renderer and APP-REBOOT-005 GUI smoke: NOT RUN because PySide6 is unavailable.
- Independent external-tool comparison: NOT PERFORMED.

## Required Windows acceptance

Run `ruff check src tests scripts`, `ruff format --check src tests scripts`,
`python -m compileall -q src tests scripts`, `python -m pytest -q`,
`python scripts/smoke_test_app_reboot_005.py` and
`.\scripts\verify_app_reboot_005.ps1` in the project's Windows Python 3.13
and PySide6 environment. APP-REBOOT-005.2 is not accepted as complete until these
Windows checks, including the real Qt movement and persistence smoke, pass.
