# PFA-SYNC-001 — Canonical Engineering Model Integration

## Scope delivered

PFA-SYNC-001 adds a canonical projection path from `NetworkWorkspace.network` to an
immutable `DiagramDocument`. The electrical `Network` aggregate remains authoritative for
bus/equipment identity, terminal cardinality and terminal-to-bus connections. The diagram
projection reads that aggregate and presentation metadata; it never creates electrical
connections from crossings or coordinates.

### Data flow

`Network + explicit terminal connections + workspace drawing metadata`
→ `project_network_to_diagram()`
→ `DiagramDocument`
→ `render_engineering_svg()` / `export_engineering_pdf()` / Qt Network Canvas.

The Workbench's SVG/PDF export action now uses this same canonical projection. The Qt canvas
projects bus and equipment identities before rendering; projection errors are shown in the
canvas instead of silently omitting unconnected equipment.

## Canonical object support

- Bus: canonical `Bus`, persistent UUID and line-to-line nominal voltage.
- Equivalent-source boundary: `UnresolvedSingleTerminalEquipment` with confirmed REF-3PH-001
  base/Z1 evidence and unresolved prefault voltage, Z2 and Z0. It is deliberately not a
  calculation-ready `EquivalentSource`.
- Generator boundary: unresolved one-terminal equipment with nameplate and sequence fields
  explicitly unresolved. It is deliberately not a `SynchronousGenerator`.
- Circuit breaker: canonical `SwitchingDevice`, two explicit terminals and OPEN/CLOSED state.
- Transformer and line bays: canonical topology-bearing two-terminal placeholders with
  explicit terminal voltages, UUIDs and named unresolved parameter evidence. They are not
  numerical `TwoWindingTransformer` or `Line` models until verified nameplate/sequence data
  are supplied.
- All projected equipment must map bijectively to a symbol; every terminal must be connected;
  every terminal-to-bus connection must map to a conductor.

The existing `TwoWindingTransformer`, `Line`, `EquivalentSource`, `SynchronousGenerator`,
and switching-device numerical models are not modified. Unresolved placeholders generate
calculation-blocking diagnostics. The numerical solver must not use drawing geometry.

## Persistence

The JSON network document persists canonical equipment, terminals, terminal-to-bus connections,
drawing positions, rotations, source-pinned diagram placements and editable labels. The current
schema version remains 1.4 to preserve the established repository contract; the new equipment
`kind` records are additive variants handled by this application version. Existing schema
1.0–1.4 documents remain readable.

## Diagram projection and quality checks

`validate_diagram_document()` checks:
- network identity;
- equipment/symbol bijection;
- terminal/symbol coverage;
- terminal-to-conductor bijection;
- positive symbol dimensions;
- orthogonal conductor segments;
- conductor intersections with unrelated equipment envelopes;
- approximate annotation/equipment collisions.

Labels are first-class presentation annotations. Existing `DiagramSymbolPlacement.label` is
used for editable equipment labels and survives save/reopen. Equipment dimensions are assigned
from the symbol-family profile; Qt and SVG consume the same projected dimensions and orientation.

## Code & Automation worker

`ScriptProject` now exposes typed methods for buses, switching devices, unresolved branches and
unresolved one-terminal equipment. These methods create the same domain objects used by the
Workbench.

`worker.py` executes scripts in a child Python process and serializes the resulting
`NetworkWorkspace` through `JSONNetworkDocumentRepository`. `worker_client.py` provides
synchronous and asyncio clients with timeout/termination. `qt_worker.py` uses `QProcess` and
supports cancellation without blocking the Qt event loop. `CodeAutomationStudio` now uses this
controller rather than executing scripts in the GUI process.

The worker enforces a narrow AST/API policy and does not permit import statements or direct
file-opening builtins. A child process plus Python-level restrictions is **not a hardened OS
sandbox**. Only trusted local scripts should be run; no claim of hostile-code isolation is made.

## Reference scenarios

Three `.network.json` files under `outputs/pfa_sync_001_canonical_scenarios/` are built from
actual `Network` aggregates and reopened through `JSONNetworkDocumentRepository` before
projection. Their SVG/PDF/PNG files are generated from the resulting `DiagramDocument`.

1. Single bus: 4 buses, source boundary, closed breaker, unresolved transformer and unresolved line.
2. Double bus: two busbars, open coupler, two unresolved feeder-line bays.
3. Multi-bus: four buses, source boundary, generator boundary, two unresolved lines and an
   unresolved transformer.

The only numeric source values are those already declared in REF-3PH-001: 100 MVA base,
13.8 kV base and positive-sequence Z1 = 0.08 + j0.24 pu. The prefault voltage, Z2 and Z0 are
not supplied and remain unresolved. Transformer, line and generator parameters remain
unresolved. The figures are therefore topology/documentation fixtures generated from real
canonical model objects, **not calculation-ready network studies**.

## Verification evidence

- Full suite: 601 passed, 4 skipped (final full-suite run).
- PFA-SYNC integration suite: 12 passed.
- Integration covers all three model scenarios, save/reopen/regenerate, bijective topology
  projection, geometry/electrical-model independence, unresolved-parameter calculation blocks,
  SVG/PDF export, script worker API, import/file access rejection, timeout cancellation and
  persisted editable labels.
- `compileall` passes for source and examples.
- PySide6 and Ruff are not installed in the execution environment. Qt runtime smoke tests,
  interactive editing, QProcess GUI cancellation, Windows PowerShell 5.1 application and
  visual acceptance in the actual Workbench remain unverified.

## Known limitations

- The current canonical scenario models deliberately retain unresolved transformer/line/generator
  data; numerical study readiness is blocked until the engineering values and provenance are
  supplied.
- The current symbol profiles cover buses, sources/generators, two-winding transformers,
  breakers, disconnectors/earthing switches and line branches. Load, protection and instrument
  transformer symbol mappings still need dedicated domain objects and reviewed symbol definitions.
- Automatic layout uses topology-aware breadth-first layering and explicit layout overrides;
  it is not yet a globally optimized substation bay planner.
- Qt label editing and position persistence are implemented but need Windows runtime validation.
  Full undo/redo for text edits, symbol resize handles, terminal snapping in the Qt interaction
  loop and comprehensive multi-selection remain open.
- PDF is generated from the same SVG vector source through CairoSVG; publication-grade font
  embedding, title blocks, legends, captions and multi-panel paper templates remain incomplete.
- The current SVG symbols are internal engineering glyphs with explicit family/state semantics.
  This increment does not claim IEC 60617 certification or Q1 publication acceptance.

## Non-goals / protection

No ND-001 through ND-016 model or numerical formulation is modified. No public repository,
release, account, donation provider or sponsorship destination is created or published.
