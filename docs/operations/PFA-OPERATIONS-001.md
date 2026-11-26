# PFA-OPERATIONS-001 — Operating scenarios and energized topology

## Purpose

PFA-OPERATIONS-001 adds an operational layer over the canonical physical `Network`.
A switching operation changes the scenario, **not** the physical terminal-to-bus
connections stored in `Network`. This is the intended separation between physical
topology and operating state.

The package provides:

- immutable `OperatingScenario` objects with switch-position, equipment-availability
  and source-availability overrides;
- structural adaptation from the existing PFA `Network` aggregate;
- open/closed switching logic for circuit breakers and disconnectors;
- graph-based connected-island identification;
- source reachability and energized/de-energized bus classification;
- closed earthing/grounding-switch identification and a hazardous live-grounded-bus
  diagnostic;
- baseline-to-contingency comparison;
- JSON-compatible scenario and result serialization.

No third-party runtime dependency is added. The graph traversal uses the Python
standard library.

## Integration with PFA

The adapter follows the aggregate properties already used across PFA:

- `network.id`, `network.name`;
- `network.buses` (`id`, `name`);
- `network.equipment` (`id`, `name`, `terminals` with `id`);
- `network.connections` (`terminal_id`, `bus_id`).

PFA switching devices are detected structurally using `device_kind` and `position`.
The adapter reads `position.value` (or a string) and accepts `open`/`opened` and
`closed`/`close`/`connected` values. The result family is populated from the PFA
`device_kind` for switchgear and the canonical `equipment.family` for other equipment.
It does not call `Network.connect()` or `Network.disconnect()`.

The adapter has integration coverage against the actual PFA `Network`, `Bus`,
`Terminal`, `NetworkWorkspace` and `SwitchingDevice` classes. Those tests verify that
opening a breaker changes the operational graph while leaving `Network.connections`
and the physical `SwitchingDevice.position` unchanged.

Source classification first uses the canonical PFA `equipment.family` value
(`source`). It also recognizes explicit `equipment_kind` values and known source class
names. If the installation uses a custom source class with no source family metadata,
provide its IDs explicitly in `source_equipment_ids`.

### Use with a Network

```python
from power_fault_analyzer.operations import (
    OperatingScenario,
    OperatingTopologyService,
    SwitchPosition,
    compare_scenarios,
)

network = workspace.network
service = OperatingTopologyService()

normal = service.analyze(network, OperatingScenario(name="Normal operation"))

breaker_id = next(
    item.id for item in network.equipment
    if item.name == "CB-COUPLER"
)
contingency = service.analyze(
    network,
    OperatingScenario(
        name="Coupler open",
        switch_positions={breaker_id: SwitchPosition.OPEN},
    ),
)

impact = compare_scenarios(normal, contingency)
print(impact.to_dict())
print(contingency.to_dict())
```

Or pass the application workspace directly:

```python
result = service.analyze_workspace(workspace, scenario)
```

### Custom source identifiers

```python
source_ids = tuple(
    item.id for item in network.equipment
    if item.name in {"GRID-EQUIVALENT", "GEN-01"}
)
result = service.analyze(
    network,
    scenario,
    source_equipment_ids=source_ids,
)
```

## Semantics and assumptions

1. A branch with at least two terminals connected to distinct buses joins those buses
   when it is in service. A multi-terminal equipment item joins each distinct bus
   attached to its terminals (clique abstraction).
2. An open switch contributes no graph edge. A closed switch contributes an edge
   when it has at least two connected bus terminals.
3. An out-of-service equipment item contributes no graph edge.
4. A source is a reachability root; it is not treated as an ordinary bus-to-bus branch.
   An enabled, in-service source energizes each bus attached to its terminals.
5. Bus islands are connected components of the active graph, including isolated
   buses. An island is energized when at least one source is attached to/reachable
   within it.
6. A closed earthing/grounding switch marks its connected bus(es) grounded, but does
   not join buses together. A grounded bus that remains source-reachable emits an
   `ERROR` diagnostic. This is a topology/operational warning, not a short-circuit
   calculation.
7. The engine does not calculate load flow, voltage profile, fault current, protection
   coordination, synchronism, interlocking, switching transients or IEC 60909 results.
   It does not claim that a proposed switching sequence is safe to execute.
8. The default equipment availability is `equipment.in_service` when exposed, otherwise
   `True`. Unspecified switch states use the captured PFA `SwitchingDevice.position`.
   Unspecified sources are enabled.
9. Source detection is deliberately configurable. Verify source IDs in networks that
   use custom equipment implementations; an unrecognized custom source will not seed
   energization unless passed explicitly.

## Result contract

`OperatingTopologyResult` includes:

- each bus state (`energized` / `deenergized`), island identifier and grounding status;
- each connected island and its source equipment IDs;
- equipment availability, switch position and buses associated with its terminals;
- structured diagnostics, including `UNENERGIZED_ISLAND`, `SWITCH_OPEN`,
  `SOURCE_NOT_CONNECTED`, `EQUIPMENT_TERMINAL_UNCONNECTED`,
  `EQUIPMENT_WITHOUT_BUS_CONNECTION` and `ENERGIZED_BUS_GROUNDED`.

`to_dict()` returns JSON-compatible values. `OperatingScenario.to_dict()` and
`OperatingScenario.from_dict()` allow scenario persistence without coupling the module
to PFA's existing project repository schema.

## Files

- `src/power_fault_analyzer/operations/models.py`
- `src/power_fault_analyzer/operations/adapter.py`
- `src/power_fault_analyzer/operations/service.py`
- `src/power_fault_analyzer/operations/comparison.py`
- `tests/unit/operations/test_operating_topology.py`
- `examples/operating_scenarios_demo.py`

## Validation commands

```powershell
ruff check src tests
pytest -q tests/unit/operations/test_operating_topology.py
pytest -q
python .\examples\operating_scenarios_demo.py
```

The new module tests include both isolated snapshot tests and integration tests against
the PFA domain aggregate. The integration fixtures use PFA's actual `Network`, `Bus`,
`Terminal`, `NetworkWorkspace` and `SwitchingDevice` implementations; only a minimal
source/branch equipment fixture is used because the feature under test is topological
reachability, not impedance or load-flow calculation.
