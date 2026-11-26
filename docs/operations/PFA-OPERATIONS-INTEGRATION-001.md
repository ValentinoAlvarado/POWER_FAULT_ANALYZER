# PFA-OPERATIONS-INTEGRATION-001 — Workspace and Workbench Integration

## Architectural contract

The physical `Network` remains the canonical electrical model. Operational state is stored separately as immutable `OperatingScenario` overlays in `NetworkWorkspace.operating_scenarios`; `active_operating_scenario_id` selects the scenario visualized by the Workbench.

An operational scenario may override:

- switching-device positions;
- equipment in-service status;
- source availability.

The overlay is never applied through `SetEquipmentSwitchPosition`. That command remains a physical-model edit. Operational changes use `SetOperatingScenarioSwitchPosition` and the `NetworkWorkspaceCommands` facade.

## Persistence

Network document schema advances from 1.5 to 1.6. The `operations` section stores each scenario's JSON-compatible contract and the active scenario UUID. Schemas 1.0–1.5 remain readable; documents without an `operations` section load with no active operational scenario.

## Workbench behavior

The Operations menu supports capture of the current physical switch positions as a named scenario, activation/deactivation, modification of a selected switching device in the active scenario, and topology analysis. Scenario edits use the existing `QUndoStack` through before/after workspace snapshots and the shared `WorkspaceCommandBus`. The Workbench diagram marks the active projection as **SIMULATION ONLY**; energized/de-energized buses and operationally overridden switching symbols are visually distinguished. A scenario edit does not invalidate a short-circuit study of the unchanged physical network.

## Transaction and validation rules

The workspace validates scenario UUID identity and ensures all referenced equipment exists; switch-position overrides must target switching devices. Deleting equipment removes its references from all stored scenarios in the same transaction. Invalid scenario commands are rejected by the shared workspace bus and rolled back.

## Operational limitations

The topology projection is graph/connectivity analysis. It is not an AC load flow, protection study, switching interlock certification or field authorization. Interlocks remain heuristic graph checks. Simulated sequences must never be treated as device commands.
