# APP-001 FORMAT REPAIR — MANIFEST

**Purpose:** resolve exactly the three Ruff 0.17.6 formatting findings reported by the Windows run.

## Changed files

| Relative path | Change |
|---|---|
| `src/power_fault_analyzer/infrastructure/persistence/json_project_repository.py` | Apply Ruff line wrapping and trailing-comma formatting. |
| `src/power_fault_analyzer/interfaces/desktop/app.py` | Apply Ruff quote/wrapping formatting in the missing-PySide6 message. |
| `tests/integration/test_desktop_application_use_cases.py` | Apply Ruff call-expression formatting. |
| `scripts/verify_app001_format_repair.ps1` | Add a PowerShell 5.1 wrapper for the complete APP-001 verification gate without reinstalling dependencies. |

## Scope and integrity

- No electrical equations, solver behavior, domain rules, parameter values, tolerances, project model, persistence schema, or architecture were changed.
- Python AST dumps (`ast.dump(..., include_attributes=False)`) were identical before and after formatting for all three Python files.
- The existing test asserting four report limitations remains unchanged; no collection item was added or removed.

## Checks performed in the build environment

- `python -m compileall -q src tests scripts`: PASS.
- `python -m pytest -q`: **535 passed**.
- Ruff 0.17.6 format check: not executable in this build environment because Ruff is unavailable and package-index access failed. The three file edits follow the exact formatting changes reported in the supplied Ruff 0.17.6 output; Windows verification remains authoritative.

## File hashes

| Relative path | SHA-256 |
|---|---|
| `APP-001-FORMAT-REPAIR-README.md` | `bd4192cb0a2261b12269accb490826c4981c2c596223df920cd3269a6c4bea59` |
| `scripts/verify_app001_format_repair.ps1` | `370f42692bcde68d3a01f6809fc01e9963f9ebadbfee22ce49051f6f8340ceaa` |
| `src/power_fault_analyzer/infrastructure/persistence/json_project_repository.py` | `87ace4e198d10aec90229a3495bb9e60f63545988101ec0f42382c227c1d5158` |
| `src/power_fault_analyzer/interfaces/desktop/app.py` | `f695f19518c106588fa36a0681afc85eb38ec12f71e3f7d09f86a1307bac655f` |
| `tests/integration/test_desktop_application_use_cases.py` | `55c611df789f78467b37754d0cac64538a2623fd9a46f6ebb37b30f448d7ad7c` |
