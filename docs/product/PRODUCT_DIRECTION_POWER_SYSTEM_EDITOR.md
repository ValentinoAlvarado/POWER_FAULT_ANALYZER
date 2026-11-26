# POWER_FAULT_ANALYZER — Product Direction: Power-System Diagram & Model Studio

**Status:** Product requirements baseline, 2026-11-23  
**Scope:** Desktop engineering workbench, diagram authoring, code-driven model authoring, persistence, export, and open-source governance.

## 1. Product definition

POWER_FAULT_ANALYZER is a power-system engineering environment. Its primary document is a technically legible **single-line diagram (SLD)** backed by an authoritative electrical network model. It is not a generic circuit doodler, a flowchart editor, or a code notebook with a diagram painted behind it.

The same project must be authorable through two equivalent workflows:

1. **Graphical authoring:** place equipment, connect terminals, edit engineering properties, validate, and run studies.
2. **Code authoring:** define the same project through a versioned, typed, declarative Python API/DSL; validate and apply it to the same domain model.

The diagram is a view of the network model. Code is a separate authoring surface. Neither source code nor debug output may be drawn over the SLD.

## 2. Non-negotiable engineering rules

- A busbar is rendered as a busbar, not as a rounded rectangle/card.
- Conductors and branches are rendered as electrical connections, not decorative arrows or arbitrary colored connectors.
- Equipment symbols used as physical SLD equipment must have a documented symbol source, license, provenance, terminal geometry, and explicit mapping to a domain equipment type before insertion is enabled.
- Unmapped QElectroTech source candidates may be placed only as explicitly labelled drawing-only reference overlays. They are not physical SLD equipment, never enter topology or solver input, and are excluded from the official SLD SVG export. The library's source-asset status is not an IEC-compliance declaration.
- A symbol's visible terminals must map one-to-one to declared electrical terminals. A graphical crossing is not an electrical junction unless the connection model says so.
- Bus, branch, generator, transformer, load, shunt, breaker, disconnector, CT/VT, grounding, and protection objects must not be conflated.
- Slack/reference-bus status is a study role, not a fabricated physical component.
- Fault markers, measurement annotations, study overlays, and operating-state highlights are separate diagram layers. They are never silently inserted into the physical network.
- Diagram coordinates, routing, zoom, labels, and sheet layout must never affect numerical results.
- IEC/IEEE conformity must be stated per symbol and edition only when verified. An asset from a library is not automatically certified as standards-compliant.
- The editor must distinguish unsupported, incomplete, invalid, and verified equipment. No fake fallback symbols or placeholder equipment may be passed to the solver.

## 3. Diagramming requirements

### 3.1 SLD-first workspace

- A clean drawing sheet with optional grid; grid is off or visually subdued by default in presentation/export mode.
- Orthogonal routing, snap-to-terminal, junction dots, busbar connection points, and clear non-connection crossings.
- Automatic layout as a starting point, never as a substitute for engineering review.
- Labels placed with collision avoidance; equipment names, ratings, and IDs are separate annotation fields with per-layer visibility.
- Zoom-to-fit, zoom to selection, pan, multi-select, align/distribute, rotate/flip where the symbol permits, undo/redo, and keyboard-first operation.
- Multiple sheets and views over one electrical model: SLD, protection/control, grounding, sequence networks, and detail views. These are not independent copies of the electrical topology.
- Drawing layers: physical equipment, conductors, annotations, study overlays, and reference/background layers.
- Print/export must use page templates, title blocks, scale, margins, page numbering, revision metadata, and vector output.

### 3.2 Visual language

- Engineering-document aesthetic: restrained monochrome linework, consistent stroke hierarchy, precise alignment, legible typography, and disciplined whitespace.
- Color is reserved for selection, diagnostics, energized/de-energized states, and study-result overlays; it must not be the primary means of identifying equipment.
- No gradients, rounded cards around electrical equipment, excessive badges, emoji, decorative 3D effects, or arbitrary pictograms in the drawing area.
- The diagram must remain readable in grayscale and when printed.
- Symbol geometry and terminal positions are preserved from the licensed source unless a documented transformation is applied.

## 4. Code-driven engineering model

The code interface is a separate **Model Studio** workspace, never an overlay on the diagram.

### 4.1 DSL contract

- Versioned schema and deterministic serialization.
- Typed constructors for project, network, bus, line, transformer, synchronous machine, external grid/Thevenin equivalent, load, shunt, breaker, disconnector, CT/VT, grounding, and protection objects as their domain models become available.
- Explicit IDs or deterministic IDs, units, base quantities, terminal references, connectivity, operating status, and provenance.
- No unrestricted `eval`, arbitrary execution of imported project text, or hidden Python side effects.
- A code change is parsed into a candidate model, validated, diffed, and only then applied transactionally.
- Graphical edits update the canonical model and can be serialized back to code. Code and GUI must not maintain separate competing truths.
- Diagnostics identify file/line/field, equipment ID, terminal, and engineering rule where possible.
- Code editor supports schema-aware completion, formatting, validation, diff preview, generated snippets, and import/export.

### 4.2 Canonical model

The target architecture has three explicitly separated layers:

1. `ElectricalNetworkModel`: authoritative buses, equipment, terminals, connections, parameters, operating states, and study roles.
2. `DiagramDocument`: sheets, symbol instances, terminal anchors, routing, annotations, layers, page setup, and view state.
3. `ModelSourceDocument`: versioned declarative source, source locations, and synchronization metadata.

The current `NetworkWorkspace.diagram_positions` is an interim presentation store. It must migrate into `DiagramDocument` without changing the solver's domain contracts.

## 5. Save, recovery, and contingency requirements

- A project save is atomic: write a temporary complete project, flush, validate, then replace the prior version.
- Project schema is versioned and migration paths are tested.
- Autosave writes recovery snapshots separately from the canonical project; it must never silently overwrite the last known-good save.
- Maintain configurable rolling snapshots (count/time policy), with a visible recovery manager and restore-to-new-copy default.
- Before destructive model transformations, preserve an undoable command or transaction snapshot.
- On crash/restart, detect recoverable work and offer compare, recover, discard, or open read-only.
- Backups include the project model, diagram documents, code source, study settings, and result provenance; licensed third-party symbol binaries are referenced by asset identity and license, not blindly copied into user projects.
- Export failure must not corrupt or mutate the saved project.

## 6. Export and interoperability

Required export targets, staged by release:

- SVG: vector diagram export.
- PDF: paginated engineering drawing and report output.
- PNG: review/share preview only, not the authoritative deliverable.
- JSON: versioned native project/model interchange.
- Python DSL: editable source representation.
- CSV/XLSX: tabular equipment, connectivity, and study results.
- Later: CIM/CGMES import/export, with profile validation and explicit loss reports.

Every export must disclose omitted/unsupported fields. No silent lossy export.

## 7. Open-source community requirements

- Select and publish a clear project license before public release; do not assume all third-party assets can be relicensed with the application.
- Maintain `THIRD_PARTY_NOTICES`, asset-level provenance, license texts, pinned source revisions, and an SBOM.
- Keep application code, symbol collections, sample networks, benchmark data, and documentation under separately reviewed licensing terms.
- Never redistribute IEC commercial symbol databases or normative text without permission.
- Provide reproducible installation, deterministic tests, CI on supported Python/OS/Qt combinations, contribution guide, code of conduct, security policy, and release notes.
- Define extension points for equipment models, solvers, symbol providers, exporters, and validation rules. Plugins must not bypass domain validation.
- Publish benchmark cases and expected results with provenance and permitted reuse.

## 8. Delivery sequence and acceptance gates

### Increment A — SLD presentation foundation

- Correct busbar, source, branch, and connection visual grammar.
- Orthogonal routing and non-overlapping labels.
- Symbol preview auto-fit on dock resize.
- SVG export.
- No code/debug text inside the drawing canvas.

### Increment B — DiagramDocument and terminal-aware connectivity

- Symbol instances map to actual equipment types and terminals.
- Connection tool snaps terminal-to-terminal and creates domain connections only after validation.
- Junction/crossing semantics are explicit.
- Diagram edits are undoable and persist independently of the electrical model.

### Increment C — Model Studio / code-first authoring

- Versioned typed DSL and schema-aware editor.
- Parse → validate → diff → transactional apply.
- GUI/code round-trip equivalence tests.

### Increment D — Engineering completeness

- Transformer, load, shunt, switching, measurement, protection, and grounding workflows backed by real domain models.
- Multi-sheet and layered diagrams.
- Automatic layout and routing stress tests on large networks.

### Increment E — Reliability and open-source release

- Atomic save, autosave/recovery, rolling backups, migrations.
- PDF/print, SVG, data exports, interoperability.
- License/SBOM/CI/security/community release gates.

## 9. Current increment boundary

APP-REBOOT-003 established the initial SLD visual foundation, QET source preview behavior, and SVG export. APP-REBOOT-004 adds resizable/persistent workspace panels and rotatable drawing-only source candidates. Neither increment implements terminal-aware interactive connectivity, a code DSL/editor, autosave/recovery, PDF drawing sheets, multi-sheet documents, or full IEC/IEEE compliance. These remain explicit future acceptance gates, not implied capabilities.


## APP-REBOOT-004 — Resizable workspace, drawing placements and distribution

The engineering workspace uses explicit nested Qt splitters for the project explorer, central drawing/result workspace, and right-side equipment/properties/source-symbol panels. Splitter sizes and window geometry are persisted between sessions and can be reset from View. Panel visibility is controlled through View actions.

QElectroTech source assets can be inserted into the drawing as movable, rotatable, source-pinned **drawing placements**. They are stored in the diagram document and are explicitly marked as not electrically mapped. Inserting a source graphic does not create a domain equipment object, infer terminal connectivity, or enter the short-circuit solver. Rotation and placement changes participate in undo/redo and project persistence.

The release target remains a downloadable desktop application. A Windows x64 PyInstaller `onedir` package, GitHub Release workflow, checksum artifact and GitHub Pages download front door are provided. The download page stays disabled until an exact public repository slug and a verified release asset are configured; no fictional download URL is presented.
