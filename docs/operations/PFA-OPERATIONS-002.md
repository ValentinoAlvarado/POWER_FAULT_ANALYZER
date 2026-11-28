# PFA-OPERATIONS-002 — Switching sequences and restoration proposals

**Status:** implementation package; local package tests and actual PFA-domain integration tests pass in the supplied validation snapshot. The complete Windows repository still requires the owner's final validation after installation.

## 1. Scope

OPERATIONS-001 analyzes a single operating scenario. OPERATIONS-002 adds a sequential layer on top of that immutable scenario model:

- ordered switch operations with expected-state checks;
- deterministic simulation after every step;
- explicit, replaceable interlock rules;
- traceable evidence references for synchronism and voltage-absence checks;
- conservative restoration proposals based on open in-service ties;
- JSON journal records with atomic file replacement;
- integration tests using PFA's actual `Network`, `Bus`, `Terminal`, `NetworkWorkspace` and `SwitchingDevice` types.

All operations are **simulation and decision support only**. No API in this package writes to `Network`, calls `connect()`/`disconnect()`, changes `SwitchingDevice.position`, or sends a command to field equipment.

## 2. Public API

```python
from power_fault_analyzer.operations import (
    JsonOperationJournal,
    OperatingScenario,
    OperationPermit,
    RestorationPlanner,
    SwitchPosition,
    SwitchingSequence,
    SwitchingSequenceService,
    SwitchingStep,
)
```

### Switching sequence

Every step states the expected present position and the target position. The expected state is an optimistic concurrency guard: if the scenario no longer matches the planned state, the step is returned as blocked with `EXPECTED_SWITCH_STATE_MISMATCH`.

```python
sequence = SwitchingSequence(
    name="Isolate bus section",
    initial_scenario=OperatingScenario(name="Base condition"),
    steps=(
        SwitchingStep(
            equipment_id=breaker.id,
            expected_position=SwitchPosition.CLOSED,
            target_position=SwitchPosition.OPEN,
            instruction="Open CB-01 for the contingency study.",
        ),
    ),
)

result = SwitchingSequenceService().simulate(network, sequence)
print(result.status.value)
print(result.to_dict())
```

The execution trace preserves the result after each successful step. When an interlock blocks a step, the result contains the last valid simulated scenario and its topology, and the remaining steps are not evaluated. Permit references and sequence description are included in the JSON trace for traceability.

An empty sequence is a valid no-op. This is required so restoration planning can return an explicit incomplete proposal when it finds no feasible switch closure.

## 3. Interlocks and evidence references

The default rule set includes:

1. `GroundSwitchCloseInterlock`: blocks a grounding-switch closure if any connected bus is source-reachable in the operating-topology model. It also requires `voltage_absence_test_reference` even when the graph marks all connected buses de-energized.
2. `CloseOntoGroundedBusInterlock`: blocks closing a non-grounding switch when any connected bus is marked grounded in the scenario.
3. `ParallelEnergizedIslandsInterlock`: blocks a closure that would join separate energized islands unless a non-empty `synchronism_check_reference` is supplied.

Example permit:

```python
permit = OperationPermit(
    operator_id="operator-01",
    authorization_reference="SWITCH-ORDER-2026-001",
    synchronism_check_reference="SYNC-TEST-7781",
)
```

For a grounding switch:

```python
permit = OperationPermit(
    operator_id="operator-01",
    authorization_reference="GROUNDING-ORDER-2026-003",
    voltage_absence_test_reference="VOLT-ABS-TEST-02",
)
```

The strings are traceability references. PFA does not validate the external measurement, document, authorization or test. A non-empty evidence reference is not proof that an operation is safe. The default interlocks are deliberately conservative but not a complete operating procedure or safety case. Projects may add `InterlockRule` implementations and inject them into `SwitchingSequenceService`.

## 4. Restoration planner

`RestorationPlanner` proposes closures of open, in-service, non-grounding switches that directly join a source-reachable island to a de-energized island. It evaluates one candidate at a time, accepts it only when the graph's energized-bus set grows, and repeats deterministically until all requested target buses are energized or no candidate improves the result.

```python
contingency = OperatingScenario(
    name="Bus coupler outage",
    switch_positions={coupler.id: SwitchPosition.OPEN},
)

proposal = RestorationPlanner().propose(
    network,
    contingency,
    target_bus_ids=(bus_b.id, bus_c.id),
)

print(proposal.complete_for_target)
print(proposal.to_dict())
```

An incomplete proposal is still returned. `remaining_deenergized_bus_ids` identifies the targets the graph-based planner could not restore; `rejected_switch_ids` identifies candidate ties that failed its simulation/interlocks. The proposal is not optimized for load priority or economic cost.

### Deliberate exclusions

The planner does not calculate:

- load pickup, cold-load pickup or load-shedding priorities;
- steady-state voltage profile, power-flow feasibility or reactive-power margin;
- branch, transformer or bus thermal ratings;
- fault duty, transient stability, frequency response or protection coordination;
- synchronism measurements or dead-line/live-bus relay conditions;
- personnel clearances, grounding integrity or switching-equipment duty.

Therefore, `complete_for_target=True` means only that the targeted buses became source-reachable in the abstract operating-topology graph after the proposed closures. It does **not** mean that real-world service can safely be restored.

## 5. Operation journal

`JsonOperationJournal` serializes simulation results in a versioned JSON document and replaces the file atomically. It assumes a single writer process. It is not tamper-evident and not a substitute for a regulated sequence-of-events recorder or transactional multi-user database.

```python
journal = JsonOperationJournal("outputs/operations/operation_journal.json")
record = journal.append(result)
print(record.record_id)
print(journal.export_dict())
```

## 6. Physical-model invariant

The PFA adapter reads the physical `Network` into a `NetworkSnapshot`. Sequence steps create new immutable `OperatingScenario` overlays. They never call `Network.connect`, `Network.disconnect`, or change an equipment's physical `position` attribute. Integration tests verify that `Network.connections` and the original `SwitchingDevice.position` remain unchanged after simulation and restoration-proposal evaluation.

## 7. Validation commands

From the repository root:

```powershell
ruff check src tests
pytest -q tests/unit/operations
pytest -q tests/integration/test_pfa_operating_sequence_integration.py
pytest -q
python .\examples\operating_sequence_demo.py
```

The package-specific test suite includes model-level tests plus tests against PFA's real domain classes. A test failure elsewhere in a repository must be investigated in its own module; do not weaken or delete it to obtain a green build.

## 8. Next integration boundary

The next UI increment should consume `SwitchingSequenceResult` and `RestorationPlan` to show step status, open/closed states, energized/de-energized islands and blocked interlocks in the unifilar editor. UI interaction must only edit a scenario draft and request a simulation. It must not silently mutate the canonical physical network.
