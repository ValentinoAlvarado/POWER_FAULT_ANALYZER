# POWER_FAULT_ANALYZER — Consolidated Desktop Source

This is a consolidated working source snapshot based on the Windows-verified `PFA-WORKBENCH-004.2.3.1` state, with the keyboard shortcut implementation and the shared transformer-symbol correction integrated into the same code tree.

## Start the desktop app

Windows PowerShell, from the repository root:

```powershell
Set-ExecutionPolicy -Scope Process Bypass -Force
.\RUN_PFA_WINDOWS.ps1
```

The script uses the existing `.venv\Scripts\python.exe` and launches `power_fault_analyzer.interfaces.desktop.app`.

## Verification

Run `scripts\VERIFY_PFA_PRODUCT_CONSOLIDATED_001.ps1` from the repository root. It executes compileall, pytest, transactional/property-editor/design-route regressions, keyboard interaction tests, transformer symbol raster tests, and regenerates canonical SVG/PDF/PNG outputs beneath `outputs\current`.

## Consolidated functionality

- Verified workbench baseline: project/network open-save workflow, command transactions, inspector/property changes and diagram canvas.
- Keyboard actions: Ctrl+Z / Ctrl+Y / Ctrl+Shift+Z, Delete, Esc, arrows, zoom, grid/snap, rotate, file and study actions. Canvas-specific edit shortcuts do not take over text widgets.
- Transformer symbol: two intersecting winding circles with short external terminal leads, rendered from one parametric definition by Qt and SVG/PDF.
- Existing short-circuit and protection calculation components remain unchanged.

## Important scope boundary

This is an engineering preview source distribution, not a claim that all power-system studies or all IEC symbols are complete. Read `docs/product/PFA_PRODUCT_READINESS_2026-11-25.md` before using it for engineering decisions or distributing it. In particular, the project license is still blank and the public Windows binary build is intentionally blocked pending a license and dependency redistribution review.
