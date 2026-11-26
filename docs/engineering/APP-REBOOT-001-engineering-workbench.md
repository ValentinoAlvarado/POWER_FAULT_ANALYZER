# APP-REBOOT-001 — Engineering Desktop Workbench

## Purpose

Replace the APP-001 single-form desktop presentation with a dockable engineering workbench while preserving the validated electrical domain and numerical solver.

## Implemented in this increment

- PySide6 `QMainWindow` with File, Edit, Project, Model, Network, Analysis, View, Tools, Reports and Help menus.
- Quick-access, network-modelling and analysis toolbars.
- Dockable Project Explorer, Equipment Palette, Properties Inspector and Calculation Console.
- Central Network Design and Results workspaces.
- Qt Graphics View canvas with grid, snap, zoom, middle-button pan, rubber-band selection and movable symbols.
- Physical network creation workflows for AC buses, explicit Thevenin equivalent sources, synchronous generators and series-only transmission lines.
- Line insertion through explicit From/To bus selection; alternatively select exactly two bus symbols and use **Network → Connect Selected Buses with Line** to preselect the endpoints.
- Separate physical topology (`Network`) and diagram metadata (`NetworkWorkspace.diagram_positions`). Moving a symbol never modifies electrical connectivity.
- Topology validation and voltage-level guard for series lines; no implicit transformer is inserted.
- Project `.pfa` metadata plus a companion `.pfa.network.json` document containing physical equipment, connections, diagram positions and historical network-study result snapshots.
- Atomic JSON sidecar replacement and compatibility with sidecars that predate the optional `study_history` member.
- Background short-circuit execution through `QThreadPool` / `QRunnable`; the GUI is disabled while a study is active. The solver contract has no cancellation token, so cancellation is not advertised.
- Results workspace for phase and sequence quantities plus a scientifically plotted phase-current phasor diagram.
- Existing report exporter integration for PDF, XLSX, CSV and JSON for the active execution.
- REF-3PH-001 template materialized from the ND-016 reference dataset as one physical bus and one connected equivalent-source model.

## Electrical data path

`WorkbenchWindow` calls application services. The `RunNetworkShortCircuitStudy` use case validates the domain aggregate, constructs explicit positive/negative/zero sequence networks through `SequenceNetworkFactoryPort`, then calls the existing `ShortCircuitSolver` through `ShortCircuitSolverPort`. The Qt widgets do not contain fault equations.

The REF-3PH-001B template reads the existing ND-016 dataset; UI code does not embed result values. The smoke test checks the actual sequence-network builder and production solver output.

## Supported equipment and exclusions

Insertion workflows are currently implemented for:

- AC bus;
- Thevenin equivalent source with explicit E1, Z1, Z2 and Z0;
- synchronous generator with explicit sequence parameters and grounding;
- series-only transmission line with explicit Z1/Z2/Z0 per length.

Transformers, motors, loads, shunts, breakers, disconnectors, CTs, VTs and protection devices are not insertable in this increment. Some domain classes exist, but complete creation, persistence and calculation workflows are not wired to the desktop. The Explorer identifies these as unavailable. The current line model has zero shunt admittance by explicit construction; this is not inferred from missing data.

The Properties Inspector is read-only in this increment. Model changes occur through dedicated dialogs and application use cases. General property-edit use cases, undo/redo for physical topology operations, clipboard, automatic layout, layer management and direct terminal-drag connection are not yet implemented. Undo/redo currently applies to diagram-position changes only.

Historical results persist as numeric snapshots. Re-export of a historical report is not offered because the original report object is not yet persisted. Active-study report export uses the existing report models/exporter.

## Project persistence

A project is stored as two coordinated files:

- `name.pfa`: project metadata and Thevenin study settings;
- `name.pfa.network.json`: physical network, terminal-to-bus connections, drawing coordinates, grid/snap configuration and study history.

Copy both files to move a complete network project. The current two-file save is not a cross-file transaction; if sidecar persistence fails after the project metadata save, the user receives an error and should retry/save to a new path.

## Architecture

- Presentation: `interfaces/desktop/workbench/`.
- Application: `application/use_cases/`, `application/ports/`.
- Domain: existing `Network`, `Bus`, `Terminal` and equipment entities.
- Infrastructure: sequence network adapter and JSON network document repository.
- Composition root: `bootstrap/workbench_container.py`.

Diagram coordinates are application/presentation metadata and are never written into domain network objects or sequence-network calculations.

## Validation

Run on Windows PowerShell 5.1:

```powershell
.\scripts\verify_app_reboot_001.ps1
```

To skip dependency installation after installing `.[dev,desktop,reports]`:

```powershell
.\scripts\verify_app_reboot_001.ps1 -SkipInstall
```

The verifier runs Ruff lint/format, compileall, the full Pytest suite and an offscreen PySide6 smoke test that creates the real workbench, loads REF-3PH-001 from the ND-016 dataset, executes the production network use case and solver, verifies phase/sequence result tables, then round-trips the result history through the JSON repository.

For interactive use:

```powershell
python -m power_fault_analyzer.interfaces.desktop.app
```

## ND-016 remains independent

APP-REBOOT-001 does not close ND-016. The existing external REF-3PH-001B numerical comparison remains an individual passing case based on the user's high-precision transcription of PowerWorld Generator and Bus Records. Native PowerWorld PWB/CSV/Message Log evidence is still pending. SLG, LL and DLG PowerWorld references remain pending. The report generated after this increment records the internal 4/4 benchmark, 44/44 quantities, 4/4 electrical audits and sensitivity PASS, while the aggregate external comparison remains `not_performed`.
