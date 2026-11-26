# APP-001 — Ruff format repair

This is an incremental patch for the three files reported by Ruff 0.17.6 as not formatted after the APP-001 lint repair.

## Apply

Extract this archive into the repository root, preserving relative paths.

## Verify on Windows / PowerShell 5.1

From the repository root, run:

```powershell
.\scripts\verify_app001_format_repair.ps1
```

The verification script reuses the existing APP-001 verification gate with `-SkipInstall`, because the desktop, reports, and development extras were already installed during the previous step.

No solver, numerical parameter, tolerance, project model, persistence schema, or architecture change is included.
