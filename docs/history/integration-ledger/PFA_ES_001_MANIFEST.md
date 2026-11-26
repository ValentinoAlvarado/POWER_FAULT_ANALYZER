# PFA-ES-001 — Increment manifest

**Increment:** PFA-ES-001 — 220 kV Double-Bus Substation Engineering Slice
**Base branch:** `product-reboot`
**Expected pre-integration HEAD:** `2ce715c6e38df24f9348ed327d3cb81d04349497`
**Python:** `>=3.13,<3.14`
**Dependencies added:** none
**License changes:** none
**Push/release actions:** none

## Purpose

Provide a real, explicit domain topology for a double-bus 220 kV substation with one line bay and one transformer bay, integrate it into the Qt Workbench, persist it with schema 1.2, expose switch-state changes with undo/redo, and block calculations when external equipment parameters are not evidenced.

## Files changed

| Path | Change |
|---|---|
| `src/power_fault_analyzer/domain/enums/bus_kind.py` | Distinguishes busbar and internal connection-node roles within the current Bus aggregate. |
| `src/power_fault_analyzer/domain/enums/switching_device.py` | Defines circuit-breaker/disconnector/earthing-switch kinds and open/closed positions. |
| `src/power_fault_analyzer/domain/enums/equipment_interface.py` | Defines external equipment boundary kinds and required provenance statuses. |
| `src/power_fault_analyzer/domain/entities/bus.py` | Adds explicit bus kind metadata. |
| `src/power_fault_analyzer/domain/aggregates/network.py` | Adds identity-preserving equipment replacement for operating-state changes. |
| `src/power_fault_analyzer/equipment/switching/switching_device.py` | Adds two-terminal switchgear whose state affects connectivity, not artificial impedance. |
| `src/power_fault_analyzer/equipment/switching/__init__.py` | Exports switchgear model. |
| `src/power_fault_analyzer/equipment/interfaces/unresolved_equipment.py` | Adds explicit line/transformer boundaries and immutable parameter evidence states. |
| `src/power_fault_analyzer/equipment/interfaces/__init__.py` | Exports external equipment interface types. |
| `src/power_fault_analyzer/application/use_cases/substation_engineering.py` | Builds PFA-ES-001; validates one selected busbar per bay and readiness. |
| `src/power_fault_analyzer/application/use_cases/network_editing.py` | Adds `SetSwitchPosition`. |
| `src/power_fault_analyzer/application/use_cases/network_workspace.py` | Links graphic pins to domain equipment terminals without inferring topology. |
| `src/power_fault_analyzer/network/sequence_networks/builder.py` | Projects closed switches as ideal node merges and blocks unresolved equipment models. |
| `src/power_fault_analyzer/infrastructure/persistence/json_network_document_repository.py` | Moves network documents to schema 1.2; round-trips switches, unresolved interfaces, two-winding transformers and explicit diagram-pin mappings; retains 1.0/1.1 reads. |
| `src/power_fault_analyzer/bootstrap/workbench_container.py` | Composes the PFA-ES-001 and switch editing use cases. |
| `src/power_fault_analyzer/interfaces/desktop/workbench/network_canvas.py` | Renders busbars/internal nodes and explicitly mapped QET symbol connections. |
| `src/power_fault_analyzer/interfaces/desktop/workbench/workbench_window.py` | Adds PFA-ES-001 build command, switch operating-state edit/undo/redo and equipment inspector details. |
| `tests/unit/application/test_pfa_es001_substation.py` | Adds topology, selection interlock, calculation-block, persistence and legacy-schema tests. |
| `tests/unit/application/test_workbench_network_workspace.py` | Extends diagram terminal mapping invariants. |
| `scripts/smoke_test_pfa_es001.py` | Adds Windows/offscreen Qt end-to-end smoke for build, render and JSON rehydration. |
| `scripts/verify_pfa_es001.ps1` | PowerShell 5.1 verifier for touched-file lint/format, compile, focused regressions and Qt smoke. |
| `docs/engineering/PFA_CAPABILITY_AUDIT_20261124.md` | Records the real code capability matrix and product gaps. |
| `docs/engineering/PFA_ES_001_SUBSTATION.md` | Documents the topology, evidence requirements, acceptance and limits. |

## Test record produced in the build container

- `PYTHONPATH=src python -m pytest -q`: **564 passed, 4 skipped**.
- `PYTHONPATH=src python -m compileall -q src tests scripts`: PASS.
- Ruff lint/format: NOT RUN here; Ruff is not installed in the build container.
- PySide6 UI smoke: NOT RUN here; PySide6 is not installed in the build container. Run `scripts/verify_pfa_es001.ps1` on the Windows 3.13 development environment.
- Electrical study: deliberately BLOCKED while line and transformer boundary parameters remain unresolved. This is correct behaviour, not a failed numerical test.
- PowerWorld or other external reference: NOT RUN for this increment.

## Known design debt

`BusKind.CONNECTION_NODE` is a typed distinction inside the existing `Bus` entity, not yet a separate `ConnectivityNode` aggregate/entity. The explicit bus/terminal graph is sufficient for this bounded vertical slice but must be refactored before claiming full IEC CIM-style topology semantics.

## Integration and rollback

Apply the accompanying unified Git patch from the repository root after confirming branch and HEAD. Use `git apply --check` before applying. Roll back this increment with `git apply -R` against the same patch while the working tree contains only this patch's changes. No commit, push, license change or public release is included.
