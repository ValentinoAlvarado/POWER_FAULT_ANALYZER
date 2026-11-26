# PFA-ES-002 implementation package

This package is an incremental source patch for the PFA repository at the PFA-ES-001 baseline (`21f8a98`). It implements explicit line/remote-grid and transformer boundary resolution, input provenance, schema 1.4 persistence (backward-readable 1.0–1.3), connected-sequence-node fault mapping, sparse fault-island Thevenin reduction, and an end-to-end bus-fault/report workflow.

## Apply

From the repository root, verify the ZIP and patch SHA-256 values, then use `git apply --check` before `git apply`. Run `scripts/verify_pfa_es002.ps1` afterwards. The included unified patch is the canonical apply method; the source files are also included at their repository-relative paths for inspection.

## Delivered source

- `src/power_fault_analyzer/application/use_cases/resolve_substation_boundary.py`
- `src/power_fault_analyzer/application/use_cases/run_network_short_circuit_study.py`
- `src/power_fault_analyzer/bootstrap/workbench_container.py`
- `src/power_fault_analyzer/domain/` and `equipment/` model/persistence changes
- `src/power_fault_analyzer/infrastructure/` solver and JSON schema changes
- `src/power_fault_analyzer/interfaces/desktop/workbench/` dialog and Workbench integration
- `src/power_fault_analyzer/network/sequence_networks/` physical-bus/node mapping changes
- `tests/unit/application/test_pfa_es002_boundary_resolution.py`
- `scripts/smoke_test_pfa_es002.py`
- `scripts/verify_pfa_es002.ps1`
- `docs/engineering/PFA_ES_002_BOUNDARY_AND_FAULT_WORKFLOW.md`

## Local build-environment verification

- Focused PFA-ES-002 tests: 6 passed.
- Full pytest suite at this implementation state: 572 passed, 4 skipped.
- `python -m compileall -q src tests scripts`: passed.
- Ruff and PySide6 are not installed in the build environment. They must be verified on the user's Windows environment through the included PowerShell verifier.

The test/smoke electrical input values are synthetic fixtures only. The workflow records entered inputs as `USER_CONFIRMED`; this is not source-document authentication. It is a generic symmetrical-components bus-fault workflow, not a declaration of complete IEC 60909 compliance.
