# APP-001 Qt verification fix — manifest

## Purpose

Fix the PowerShell 5.1 native-argument quoting failure in the final desktop verification gate.

## Changed file

- `scripts/verify_app001.ps1`

## Technical change

The Qt gate previously passed Python source containing an embedded double-quoted string to `python -c` through a PowerShell native-command argument array. On the user's Windows PowerShell 5.1 execution, those embedded quotes were removed before Python received the code, producing `print(APP-001 ...)` and a `SyntaxError`.

The gate now avoids nested quotation characters entirely and performs a stronger smoke check:

1. imports `QApplication`;
2. imports and constructs the desktop composition root;
3. constructs the actual `MainWindow`;
4. asserts that the window title is non-empty;
5. prints the boolean `True` on success.

This patch changes only the verification script. It does not change application code, electrical calculations, solver behavior, domain models, persistence, dependencies, or tests.

## Application to repository

Extract the ZIP into the repository root, overwriting `scripts/verify_app001.ps1`, then run:

```powershell
.\scripts\verify_app001_format_repair.ps1 -SkipInstall
```

Expected result: Ruff lint PASS, Ruff format PASS, compileall PASS, Pytest PASS, and desktop composition/window-construction PASS.

## Validation status

The PowerShell script has been inspected and the Python `-c` payload contains no embedded quote characters. The Qt runtime must be executed in the user's Windows/PySide6 environment; this build environment cannot certify the Windows Qt platform plugin.

# APP-001 Qt verification fix — SHA-256

| File | SHA-256 |
|---|---|
| `scripts/verify_app001.ps1` | `83c1b3ae8c3341e5eb67b47059e4a70c11a8ab4b8172681b9fc67f901d79eae3` |
