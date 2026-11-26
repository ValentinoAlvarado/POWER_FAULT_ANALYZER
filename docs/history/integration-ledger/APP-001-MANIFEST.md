# APP-001 incremental patch manifest

**Increment:** APP-001 — Desktop Application Shell & Project Workspace  
**Target:** `POWER_FAULT_ANALYZER`, Python `>=3.13,<3.14`  
**Patch format:** paths relative to repository root; no solver, ND-016 dataset, tolerances or existing validation logic modified.

## Files

| Path | Purpose |
|---|---|
| `pyproject.toml` | Registers the `pfa-desktop` console entry point. Existing `desktop` and `reports` extras are reused. |
| `README.md` | Documents the first desktop workspace and launch instructions. |
| `docs/engineering/APP-001-desktop-workspace.md` | Architecture, persistence decision, scope, constraints and verification instructions. |
| `scripts/verify_app001.ps1` | PowerShell 5.1 setup and verification script for Python 3.13, Ruff, compileall, Pytest and Qt imports. |
| `src/power_fault_analyzer/domain/projects/__init__.py` | Public exports for project aggregates and settings. |
| `src/power_fault_analyzer/domain/projects/models.py` | Immutable project, Thevenin settings and numerical run snapshot models. |
| `src/power_fault_analyzer/application/__init__.py` | Application-layer package exports. |
| `src/power_fault_analyzer/application/ports/__init__.py` | Public application port exports. |
| `src/power_fault_analyzer/application/ports/project_repository.py` | Project persistence abstraction. |
| `src/power_fault_analyzer/application/ports/short_circuit_solver.py` | Production solver abstraction. |
| `src/power_fault_analyzer/application/ports/thevenin_sequence_network_factory.py` | Thevenin sequence-network construction abstraction. |
| `src/power_fault_analyzer/application/ports/study_report_exporter.py` | Report export abstraction and result DTO. |
| `src/power_fault_analyzer/application/use_cases/__init__.py` | Use-case package exports. |
| `src/power_fault_analyzer/application/use_cases/project_workspace.py` | Create, open and save project orchestration. |
| `src/power_fault_analyzer/application/use_cases/run_thevenin_fault_study.py` | Orchestrates one-bus Thevenin studies through ports and production solver. |
| `src/power_fault_analyzer/application/use_cases/export_study_report.py` | Report export use case. |
| `src/power_fault_analyzer/bootstrap/desktop_container.py` | Desktop composition root and dependency wiring. |
| `src/power_fault_analyzer/infrastructure/adapters/__init__.py` | Infrastructure adapter exports. |
| `src/power_fault_analyzer/infrastructure/adapters/short_circuit_solver_adapter.py` | Adapter delegating to existing `ShortCircuitSolver`. |
| `src/power_fault_analyzer/infrastructure/adapters/thevenin_sequence_network_factory_adapter.py` | Converts explicit sequence Thevenin impedances into the existing network model. |
| `src/power_fault_analyzer/infrastructure/adapters/engineering_report_exporter_adapter.py` | Adapter to the existing PDF/XLSX/CSV/JSON report generator. |
| `src/power_fault_analyzer/infrastructure/persistence/__init__.py` | Persistence adapter exports. |
| `src/power_fault_analyzer/infrastructure/persistence/json_project_repository.py` | Versioned `.pfa` JSON persistence with atomic replacement and study history. |
| `src/power_fault_analyzer/interfaces/desktop/__init__.py` | Desktop interface package exports. |
| `src/power_fault_analyzer/interfaces/desktop/app.py` | PySide6 application entry point. |
| `src/power_fault_analyzer/interfaces/desktop/main_window.py` | Project workspace, inputs, results, history and report actions. Presentation only; no electrical equations. |
| `src/power_fault_analyzer/interfaces/desktop/view_models.py` | Formatting of result rows for the desktop view. |
| `tests/unit/domain/projects/test_project_models.py` | Domain project validation and immutable snapshot tests. |
| `tests/unit/application/test_project_workspace.py` | Project workspace use-case tests. |
| `tests/unit/infrastructure/test_thevenin_sequence_network_factory.py` | Infrastructure network factory tests. |
| `tests/integration/test_desktop_application_use_cases.py` | End-to-end use-case integration with production solver, project persistence and report exporters. |

## Validation performed in the build environment

- `python -m compileall -q src tests scripts`: **PASS**.
- `python -m pytest -q`: **535 passed**.
- ND-016 CLI regression: **4/4 analytical cases, 44/44 quantities, 4/4 electrical audits, sensitivity PASS**. External-tool status remains `NOT_PERFORMED` in the global report.
- Wheel build: **PASS**; packaged desktop module and `pfa-desktop` entry point verified.
- Ruff lint/format: **NOT RUN**; Ruff was unavailable in the environment and package-index access was unavailable.
- Qt GUI runtime smoke test: **NOT RUN**; PySide6 was not installed in the build environment. The PowerShell verification script performs this check on the target Windows installation.

## Scope boundaries

APP-001 implements a one-bus Thevenin workspace for REF-3PH-001B. It is not a multi-bus graphical Network Editor, does not synthesize branch currents unavailable from the solver, and does not claim IEC 60909 compliance or feature parity with commercial platforms.

No changes are made to `ShortCircuitSolver`, ND-016 tolerances, benchmark datasets or existing validation algorithms.
