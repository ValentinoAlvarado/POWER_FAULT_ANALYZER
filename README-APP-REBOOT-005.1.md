# APP-REBOOT-005.1 — Qt import hotfix

Fixes Ruff F821 in `workbench_window.py` by importing `QHBoxLayout` from `PySide6.QtWidgets`.
No behavior, architecture, layout, model, solver, or persistence code is changed.

## Apply
Extract this ZIP at the repository root, preserving the relative path. It replaces exactly one source file.

## Verify
```powershell
ruff check src tests scripts
ruff format --check src tests scripts
python -m compileall -q src tests scripts
python -m pytest
.\scripts\verify_app_reboot_005.ps1
```
