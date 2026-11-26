# APP-001 — Ruff repair increment

## Purpose

Repair the 11 Ruff findings reported by the first Windows execution of `scripts/verify_app001.ps1` after APP-001 was extracted. This is an incremental source patch for the integrated APP-001 branch; it is not a replacement repository and must be extracted at the repository root.

## Changed files

| Relative path | Change |
|---|---|
| `src/power_fault_analyzer/application/use_cases/run_thevenin_fault_study.py` | Parenthesize the two concatenated limitation strings inside the tuple. The application still contributes exactly two strings. |
| `src/power_fault_analyzer/domain/projects/models.py` | Replace `TypeAlias` declaration with Python 3.13 `type ComplexPair = ...`; remove unused import. |
| `src/power_fault_analyzer/interfaces/desktop/main_window.py` | Reorder Qt imports; remove redundant conditional; catch expected I/O, input, calculation and report-export exceptions instead of blind `Exception`; simplify dirty-state expression. |
| `tests/integration/test_desktop_application_use_cases.py` | Assert the two application limitations remain separate and preserve the report builder's two additional default limitations. |
| `scripts/verify_app001_ruff_repair.ps1` | PowerShell 5.1 wrapper that verifies patch integration and reruns the existing APP-001 verification script. |

## ISC004 safety

No `--unsafe-fixes` were used. The two use-case limitations are explicitly parenthesized as separate tuple expressions. A regression test checks their individual text and confirms the complete report contains four limitations: the two use-case limitations plus the two existing report-builder defaults.

## Exception boundaries

- Open/save project: `OSError`, `TypeError`, `ValueError`.
- Execute study: `ArithmeticError`, `OSError`, `RuntimeError`, `TypeError`, `ValueError`.
- Export report: `OSError`, `RuntimeError`, `TypeError`, `ValueError`.

Unexpected programming errors are no longer swallowed by broad `except Exception` handlers.

## Validation performed in the build environment

- `python -m compileall -q src tests scripts`: PASS.
- `python -m pytest -q`: **535 passed**.
- `python -m power_fault_analyzer.validation --json outputs/nd016-validation-report-app001-ruff-repair.json`: PASS; 4/4 analytical cases, 44/44 quantities, 4/4 electrical audits, sensitivity PASS (`4.481e-07`); external comparison for the complete ND-016 suite remains `NOT PERFORMED`.

Ruff 0.17.6 could not be executed in the build environment because it is not installed there and package-index access failed (DNS). The reported findings were addressed manually. The authoritative Ruff lint and format checks must be rerun in Windows, where Ruff 0.17.6 is installed.

PySide6 was successfully installed in the user's Windows environment per the provided log. This patch does not alter the solver, benchmark data, tolerances, project schema or application architecture.

## Integration

Extract this ZIP at the repository root, then execute:

```powershell
.\scripts\verify_app001_ruff_repair.ps1
```

The wrapper calls the existing `scripts/verify_app001.ps1`, which repeats the editable installation and all APP-001 quality gates.
