# APP-001 — Desktop Application Shell & Project Workspace

## Scope

APP-001 introduces the first executable PySide6 desktop workspace. It creates,
opens and saves a versioned `.pfa` project file; edits a single-bus Thevenin study;
executes the existing `ShortCircuitSolver` through an application port; displays
phase and sequence results; records numerical run snapshots; and exports the
existing engineering report model to PDF, XLSX, CSV and JSON.

This increment is deliberately not a multi-bus network editor. The project input
is an explicit Thevenin equivalent at one physical bus. No electrical equations
are implemented in the Qt presentation layer.

## Layer boundaries

- **Presentation:** `interfaces/desktop` (PySide6 widgets and display-row formatting).
- **Application:** `application/use_cases` and `application/ports` (workspace,
  run-study and export orchestration).
- **Domain:** `domain/projects` and the existing fault/network/result models.
- **Infrastructure:** numerical solver and report adapters plus the JSON project
  repository.
- **Composition root:** `bootstrap/desktop_container.py`.

The `NumericalShortCircuitSolverAdapter` delegates directly to the production
`ShortCircuitSolver`. The application use case obtains the model from the
`TheveninSequenceNetworkFactoryPort`; its infrastructure adapter maps explicit
sequence impedances into Norton shunts. This is network-model construction, not a
second fault-calculation engine.

## Project persistence decision

The `.pfa` project is a schema-versioned JSON document written atomically. It
stores project metadata, editable Thevenin inputs and a numerical snapshot of each
completed study (phase and sequence quantities plus the settings used for that
run). SQLAlchemy/SQLite are not introduced in APP-001: this local, portable
single-project document has no query, concurrent-write or relational requirements
that justify a database dependency. Revisit SQLite when project catalogs,
searchable multi-project history, background jobs or concurrent clients are added.

## REF-3PH-001B defaults

- Base: 100 MVA, 13.8 kV line-to-line.
- Prefault positive-sequence voltage: `1.02 + j0.025` p.u.
- `Z1 = 0.08 + j0.24` p.u.
- `Z2 = 0.11 + j0.31` p.u.
- `Z0 = 0.18 + j0.52` p.u.
- Three-phase fault: `Zf = 0.025 + j0.070` p.u.

The defaults are editable. All values are passed to the existing solver in their
specified units. A balanced three-phase fault uses the positive-sequence network
in the current solver; negative- and zero-sequence values remain stored for other
fault classifications supported by the solver.

## Install and run (Windows PowerShell 5.1)

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev,desktop,reports]"
python -m power_fault_analyzer.interfaces.desktop.app
```

Or run the `pfa-desktop` entry point after editable installation. In PyCharm,
select the `.venv` interpreter and set the run target to
`power_fault_analyzer.interfaces.desktop.app` (module) or `pfa-desktop` (script).

## Verification

```powershell
python -m ruff check src tests
python -m ruff format --check src tests
python -m compileall -q src tests scripts
python -m pytest -q
```

PySide6 is optional at package-install time and is required only to launch the GUI.
Application/use-case tests do not import Qt. The GUI itself must be smoke-tested
on Windows with the installed Qt runtime before a desktop release is declared.

## Explicit non-claims

APP-001 does not implement a graphical multi-bus network editor, arbitrary project
network modelling, branch-current reconstruction, protection UI, or IEC 60909
conformance. It does not turn the existing single-bus Thevenin workflow into a
PowerFactory/ETAP/PowerWorld feature-equivalent product.
