# PFA-DESIGN-003 — Engineering Diagram Composition & Symbol System

**Status:** implemented in the incremental payload; Windows runtime verification is part of the installer.  
**Compatibility:** Python 3.13; existing PFA-SYNC-001 canonical `NetworkWorkspace`.  
**Scope:** presentation, symbol projection, diagram annotations, and Workbench rendering. No numerical model from ND-001 through ND-016 is changed.

## 1. Canonical model remains authoritative

`Network`, its equipment identities, terminal identities, and `Network.connections` remain the sole electrical topology source. The projection does not infer connectivity from line crossings, visual proximity, symbol overlaps, or drawing coordinates.

`project_network_to_diagram()` produces a `DiagramDocument` with four separate collections:

- buses with finite busbar extents and orientation;
- equipment symbols with equipment UUID, symbol definition ID, terminal UUIDs, terminal designations, terminal coordinates, orientation, and dimensions;
- conductors whose `terminal_id` and `bus_id` reproduce the canonical terminal-to-bus links;
- independent annotation objects.

Two-terminal line equipment is rendered as a conductor-bearing branch between its two canonical terminal coordinates. It is not represented by an invented box. Bus taps are clamped to the finite busbar segment, so a wire cannot silently connect to an infinite bus axis.

`validate_diagram_document(workspace, document)` checks identity and cardinality, equipment/symbol bijection, terminal coverage, terminal-to-bus correspondence, positive symbol dimensions, terminal endpoint correspondence, orthogonal connection drops, and label collisions with equipment, busbars, conductors, and other labels.

## 2. Automatic composition and routing

A connected path topology is ordered from a source-priority endpoint and arranged as a two-column diagonal serpentine: every bus receives a distinct row, while X alternates between compact columns. This keeps the figure wider than a single vertical stack without placing adjacent buses on the same horizontal axis. Busbars remain horizontal; all two-terminal bay equipment is oriented vertically between its connected bus rows. Branch conductors leave and enter horizontal bars vertically, with a short orthogonal dog-leg only after leaving the bar. One-terminal sources are placed above horizontal busbars and generators below them.

Branching, disconnected, and cyclic structures use a deterministic breadth-first row assignment; every bus receives a unique Y coordinate. Explicit user diagram positions and rotations remain presentation metadata and take precedence over automatic bus placement. Double-bus main bars and feeder terminal bars remain horizontal, while breaker/line equipment is moved into separate vertical bays. Bus names and nominal voltages are placed beyond the physical right end of each bar so tap drops do not pass through text. The automatic layout is not claimed to be globally optimal for arbitrarily large cyclic networks; complicated meshes may require manual lane assignment.

Each canonical terminal receives a dedicated, evenly distributed physical tap on its busbar. Tap assignment is stable by equipment family, equipment name, and terminal designation; two different terminals on the same bus are not collapsed onto one geometric point. Each conductor starts with a segment normal to the busbar and terminates with a segment axial to the vertical equipment pin. A geometric intersection never creates an electrical node.

## 3. Symbol catalogue and traceability

`diagram/symbol_catalog.py` holds the built-in symbol definitions. Each definition records:

- stable PFA symbol ID and equipment family;
- width and height in drawing units;
- terminal designations and local terminal coordinates;
- a visual description;
- source/provenance and licence description;
- definition SHA-256.

The catalogue currently contains busbar, equivalent source, synchronous generator, two-winding transformer, circuit breaker, disconnector, earthing switch, line branch, and generic unresolved one-terminal symbols.

**Normative limitation:** the catalogue records an intended IEC 60617 cross-reference, but every current definition is marked `NOT_VERIFIED`; the cross-reference and edition are explicitly pending verification. The geometry is project-authored. This delivery does not claim IEC conformity or reproduce licensed commercial IEC artwork. QET and other third-party symbol sources remain governed by their own provenance and licence review.

## 4. Labels are separate editable objects

`EngineeringLabel` is independent of equipment and busbar geometry. It stores a stable UUID, optional owner UUID, text, anchor, X/Y position, font family, typographic point size, weight, color, rotation, visibility, layer, priority, unit, and number-format metadata.

The projection first places labels near their owner, then tests nearby two-dimensional offsets against geometry and previously placed labels. It attempts small horizontal corrections before moving an annotation farther vertically. It does not change the owner or canonical equipment name.

In Qt, `DiagramLabelItem` is a separate editable and movable `QGraphicsTextItem`. Double-click text editing and dragging update `NetworkWorkspace.diagram_labels`. Its context menu adjusts font family, font size, bold weight, text color, and text anchor; these values are persisted alongside the position. Moving a bus or canonical equipment object also moves its owned labels. Conductors are recalculated from the moved symbol terminals and the bus tap. This interaction is implemented in `network_canvas.py`; the Qt runtime is not available in the Linux build container and is therefore verified by the Windows smoke script, not claimed as locally executed here.

## 5. Persistence and Code & Automation

The JSON network document schema advances to **1.5** to persist independent diagram labels. The reader continues to accept versions 1.0 through 1.4; labels are empty when loading older schemas.

`ScriptProject.set_diagram_label()` and `ScriptProject.add_annotation()` write to the same `NetworkWorkspace` label collection used by the Workbench. They do not create a second drawing model and do not alter electrical topology. This keeps manual editing, automation, persistence, and vector export on the same canonical workspace.

## 6. SVG, PDF, and figure presets

`render_engineering_svg()` and `export_engineering_svg()` preserve the conductor, equipment, and annotation layers as vector elements. Text labels remain individual SVG `<text>` nodes with stable IDs and per-label styling. Symbol groups carry symbol IDs, family, terminal IDs, provenance, licence, normative status, and definition hash.

`export_engineering_pdf()` converts the SVG document to vector PDF through CairoSVG. `export_engineering_png()` creates review rasters from that same SVG source; PNG is not the master document. CairoSVG is declared in both the desktop optional dependency group and `requirements-desktop.txt`.

The current presets are:

- `single-column`: 88 × 62 mm;
- `double-column`: 180 × 120 mm;
- `landscape`: 180 × 92 mm.

The page dimensions are physical dimensions. Font sizes and line widths are typographic point values mapped into the SVG viewBox; viewBox bounds account for symbols, conductor geometry, and text extents.

## 7. Unresolved information is visible, not fabricated

Unresolved equipment parameters remain marked with `†`; incomplete sequence-network data remain marked with `‡`. Each condition is described once in the document key rather than repeated as long text over the network. The underlying unresolved equipment models remain unresolved and continue to block calculations through the existing validation service. No impedance, rating, sequence data, or other electrical parameter is invented by this design increment.

## 8. Verification performed in the build container

- `python -m compileall -q src scripts tests`: PASS.
- `PYTHONPATH=src pytest -q -rs`: **611 passed, 4 skipped**.
- The four skips are existing Qt symbol tests skipped because PySide6 is not installed in this Linux container.
- All three canonical projections report zero projection diagnostics and pass topology/terminal correspondence validation.
- SVG and PDF files were produced for all three canonical scenarios. PDFs were rendered to PNG using the PDF skill renderer and visually inspected; no clipping or malformed glyphs were observed in the inspected output.

**Windows-specific limitation:** Qt runtime behavior, Workbench drag/edit interactions, and the Windows installer must be verified in the user's Windows Python environment. `VERIFY_PFA_DESIGN_003.ps1` runs the complete pytest suite and the three-scenario Qt canvas smoke test after applying the package. This document does not represent a claim that the Linux container executed PySide6.

## 9. Acceptance boundaries

This increment improves the canonical projection, composition, symbols, label model, Workbench rendering path, and vector export. It does not certify the complete application against every IEC 60617 symbol, replace a full electrical-engineering review, or guarantee globally optimal layout for all arbitrary graph structures. Those claims require a separately controlled symbol-to-standard crosswalk, additional topologies, and in-environment engineering review.


## 10. Qt branch signal regression (PFA-DESIGN-003.1)

`BranchSymbol` remains a `QGraphicsPathItem` so that its existing path rendering,
selection, hit testing, and item geometry are retained. Because `QGraphicsPathItem`
is not a `QObject`, Qt signals are owned by a private `_BranchSymbolSignals`
`QObject` carrier. The public `moved` and `move_committed` properties expose its
bound signals without changing the Workbench connection API. Initial placement is
guarded so the constructor does not publish a user-movement event while setting
its first position. A Qt regression test exercises construction and subsequent
position-change signal delivery; the Windows verifier also constructs the actual
three canonical canvases, including their branch graphics items.


## 11. Qt graphics-item initialization and signal ownership (PFA-DESIGN-003.2)

The canvas distinguishes Qt graphics classes by QObject ownership. `BusSymbol`,
`CanonicalEquipmentSymbol`, and `SourceSymbol` derive from `QGraphicsObject`;
their `moved` and `move_committed` signals are native QObject signals and are
emitted through `self.moved` / `self.move_committed`. Their constructors establish
an `_initializing` guard before setting item metadata and release it only after
construction, preventing a virtual `itemChange()` callback from observing an
uninitialized guard. `itemChange()` uses a defensive default that suppresses
notifications until initialization has completed.

`BranchSymbol` derives from `QGraphicsPathItem`, which is not a QObject. It
continues to use `_BranchSymbolSignals(QObject)` as a signal carrier. The carrier
is deliberately limited to that class; it is not referenced by QObject-based
symbols. Runtime regression tests exercise a branch and all three QObject-based
symbol classes, while a Qt-independent AST contract test protects the distinction
in environments without PySide6.


## 12. Terminal-incidence bus sizing, explicit Qt nodes, and switch-function marks (PFA-DESIGN-003.3)

Busbar length is now determined from the count of canonical terminal-to-bus connections, not the count of adjacent bus objects. The minimum is 160 drawing units, each additional connected terminal adds 36 units, and the length is capped at 280 units. This accounts for shunt sources, generator connections, line terminals, and switching-device bays; a one-neighbour bus with multiple real connections is no longer incorrectly sized as a feeder stub.

The Qt Workbench now renders a filled connection marker at each canonical bus tap, matching the junction overlay already emitted by SVG/PDF. Each marker is keyed by terminal UUID and is repositioned when its connected bus or equipment moves. The dot is a presentation of a real `Network.connections` entry; it is never inferred from a graphical crossing.

Circuit-breaker and disconnector symbols now use distinct candidate function marks: a cross for the circuit-breaker function and a transverse bar for the disconnector function. The catalogue cross-references IEC 60617 symbols 07-13-05 and 07-13-06 as candidates only. The normative status remains `NOT_VERIFIED` until the symbol-by-symbol geometry and edition are reviewed against the licensed IEC catalogue.


## 13. Perpendicular busbar bays and canonical tap allocation (PFA-DESIGN-003.4)

The Windows evidence review of the PFA-DESIGN-003.3 single-bus figure exposed a semantic drafting defect: adjacent bus nodes had been placed on the same Y coordinate, and their breaker/line/transformer equipment followed the horizontal center-to-center axis. The result looked like one continuous busbar interrupted by equipment. That geometry was removed.

PFA-DESIGN-003.4 gives each bus a distinct row, alternates path buses across two compact X columns, and places every two-terminal equipment symbol vertically between the connected bus rows. The first and final conductor segments are normal to the horizontal busbar/equipment pin; intermediate routing is orthogonal. The double-bus fixture now has separately assigned bay corridors so the coupler and outgoing feeder branches do not share a horizontal bus axis.

`_terminal_bus_taps()` assigns a distinct tap to each canonical terminal-to-bus connection, with deterministic ordering and an end margin. SVG/PDF and Qt use those physical locations. During Qt movement, `NetworkCanvasView` stores each tap's scalar offset along its bus axis, so dragging a bar preserves bay spacing instead of snapping all terminals toward the same nearest point. The Qt smoke test now checks perpendicular first/last conductor segments, unique tap positions before/after dragging, marker movement, and all three canonical network scenarios.

This is a geometry/presentation correction only. `Network`, its equipment UUIDs, terminal UUIDs, and canonical `Network.connections` are unchanged. The two-terminal source/transformer/line placeholders remain unresolved where their electrical parameters were not supplied. The built-in symbols remain project-authored geometry with IEC cross-reference state `NOT_VERIFIED`; no normative conformity claim is made.


## 14. Minimum-length perpendicular bay routing (PFA-DESIGN-003.5)

The 003.4 user-render review identified unnecessary lateral dog-legs caused by
independent tap allocation at the two ends of a two-terminal bay. The allocator
now reserves one common scalar lane for both terminals whenever the finite
busbar extents overlap. The equipment center and both terminal pins are placed
on that same lane. One-terminal shunts are centered directly above/below their
own reserved tap rather than at the bus center. Adjacent automatic bus columns
are brought closer so the finite bar extents share a larger bay corridor.

The default canonical scenarios therefore use a single straight conductor
segment perpendicular to the horizontal busbar. When a user manually moves a
bus or equipment away from its reserved lane, the router uses the shortest
Manhattan path compatible with the required perpendicular departure from the
bus and axial arrival at the equipment pin. Its path length is checked against
the Manhattan lower bound; a non-minimal orthogonal detour is a projection error.
The Qt canvas applies the same rule while dragging: tap offsets remain fixed on
the bar, the route stays orthogonal and its Manhattan length remains minimal.

The automatic path columns are now 60 drawing units apart rather than 140,
which enlarges the overlap between finite bars and reduces lateral bay travel.
One-terminal source/generator symbols are kept 72 units from the bar centerline
inside the adjacent bay envelope; this avoids the previous placement beyond
the next bus row. Terminal lanes use a 56-unit preferred separation to reduce
overlap between transformer, line, and shunt symbol envelopes, relaxing only
when manually placed busbars leave insufficient shared extent.

This change remains presentation-only. It neither changes terminal-to-bus
associations nor introduces connectivity through geometric crossings.

## PFA-DESIGN-003.6 — Shared minimum-length Qt/SVG/PDF routing

Qt interactive routing and canonical SVG/PDF projection now call the same
`perpendicular_bay_route` geometry function from `diagram/layout.py`. An aligned
terminal-to-bus attachment is represented by exactly two path points (one
straight perpendicular segment); redundant collinear waypoints are removed.
After a bus is dragged, a single orthogonal dog-leg is used only when required
by the offset. For non-degenerate routes its length equals the Manhattan lower
bound while preserving perpendicular bus departure and terminal approach.
The helper is independently covered by tests that run without the Qt runtime.
