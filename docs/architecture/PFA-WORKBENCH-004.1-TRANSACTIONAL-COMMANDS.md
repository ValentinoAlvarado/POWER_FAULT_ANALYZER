# PFA-WORKBENCH-004.1 — Transactional Workspace Commands

**Status:** implemented in the cumulative source snapshot.  
**Scope:** application-level command boundary shared by the Qt Workbench and Python Code & Automation.  
**Electrical model changes:** none. ND-001 through ND-016 remain untouched.

## 1. Decision

All supported interactive workspace edits are dispatched through
`NetworkWorkspaceCommands`, backed by `WorkspaceCommandBus`. A command receives
one canonical `NetworkWorkspace`; it does not receive a separate GUI or scripting
model. Qt widgets and `ScriptProject` use the same command facade and command types.

The command bus is the application transaction boundary. It is deliberately
independent of Qt so the scripting API, tests and future non-GUI adapters can use
it without importing PySide6.

## 2. Atomic execution

`WorkspaceCommandBus.execute(command)` and `execute_many(commands)` perform these
steps under a re-entrant lock:

1. Check command contracts and an optional optimistic `expected_revision`.
2. Deep-copy the complete workspace as a rollback memento.
3. Execute the command or command batch against the existing workspace object.
4. Re-run `NetworkWorkspace` invariants after mutation.
5. Commit one revision and publish one immutable `WorkspaceCommandEvent`.
6. If command execution or invariant validation fails, restore all workspace
   dataclass fields from the memento and publish no event.

Event subscribers are observers only. An observer exception is logged and cannot
undo an already committed domain transaction. Event history is bounded to the
most recent 1,000 commits.

## 3. Implemented command set

| Command | Responsibility | Topology impact |
|---|---|---|
| `AddBus` | Create a validated AC bus and initial drawing position | Adds a bus; no inferred connections |
| `AddTheveninSource` / `AddSynchronousGenerator` / `AddTransmissionLine` | Invoke the existing validated application use cases | Explicit terminal-to-bus associations only |
| `RegisterEquipment` | Register a prebuilt equipment entity and its explicit terminal-to-bus pairs atomically | Uses aggregate validation; no geometric inference |
| `MoveDiagramElements` | Move one or more known electrical identities in presentation space | None |
| `MoveDiagramSymbol` | Move/rotate an existing drawing placement | None |
| `RotateBusbar` | Change the busbar's diagram orientation | None |
| `UpsertDiagramLabel` | Add/update independently editable annotation metadata | None |
| `UpsertDiagramSymbol` | Add/update a source-pinned drawing placement | None |
| `SetEquipmentSwitchPosition` | Update a real switch through the existing domain use case | Operating state only; terminal identities preserved |
| `UpdateBus` | Replace a bus revision while retaining its identity and network connections | Preserves connection IDs and references |
| `RemoveBus` | Remove an unconnected bus and its presentation metadata | Aggregate rules reject in-use buses |
| `RemoveEquipment` | Remove equipment and its terminal connections plus owned drawing metadata | Uses aggregate removal semantics |
| `RemoveDiagramSymbol` | Remove a drawing-only placement | None |
| `SetDiagramGrid` | Update grid and snap settings | None |

`execute_many` groups multiple commands into one atomic commit. A failure in any
command restores all commands in that batch.

## 4. Workbench integration

The Qt Workbench retains its existing `QUndoStack` for user-facing undo/redo.
Its command applications now go through `NetworkWorkspaceCommands`: bus creation,
committed element movement, bus rotation, switch state changes and annotation or
symbol placement updates. Thus QUndoStack's redo/undo callbacks invoke the same
transactional application boundary as automation commands.

During a drag, Qt may update the live scene/workspace presentation state for
continuous feedback. The committed edit is then passed through the command facade;
its transaction snapshot is taken at commit time. Electrical topology is never
inferred from scene geometry.

## 5. Code & Automation integration

`ScriptProject.commands` exposes `NetworkWorkspaceCommands` for the exact
`NetworkWorkspace` returned by `ScriptProject.render()`. `ScriptProject.network`
is a property backed by `workspace.network`, so a transaction rollback cannot
leave a stale aggregate alias. The script convenience operations for adding a
bus, moving a diagram element, rotating a busbar, changing a switch position and
writing labels use that same facade.

Example:

```python
project = ScriptProject("Feeder study")
bus = project.add_bus("BUS-13K8", 13.8, x=240, y=160)
project.move_diagram_element(bus, 320, 200)
project.rotate_bus(bus, 90)
print(project.commands.revision)
```

## 6. Revision and concurrency contract

Each successful single command or command batch increments the bus revision once.
Callers that have read a revision can supply `expected_revision` to reject stale
writes. One bus instance serializes its own commits. Multiple independently constructed
bus instances do not share a lock or revision counter; the composition root binds
one facade to each active Workbench workspace. This is not a distributed lock and
does not claim multi-process concurrency control.

## 7. Deliberate boundaries

- This increment does not alter electrical calculation models or standards logic.
- It does not implement a second undo stack; the Qt Workbench's existing
  `QUndoStack` remains the UI undo/redo authority for now.
- It does not make arbitrary Python object mutations transactional. Automation
  code must call the exposed `project.commands` facade for edits that require
  rollback, revision events and validation.
- Equipment property forms, full selection/multi-edit, layer operations and
  process-level script isolation remain subsequent Workbench increments.
