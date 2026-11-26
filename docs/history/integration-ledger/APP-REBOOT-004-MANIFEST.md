# APP-REBOOT-004 — Resizable engineering workspace and rotatable source drawing candidates

Commit: `fe660f7`  
Parent/base used by this patch: `6caab0f`  
Target user branch from the validated Windows session: `product-reboot` at `d0639ad`.

## Included

- Replaces the static right/left engineering panel layout with nested resizable Qt splitters and visible grip handles.
- Adds persistent splitter sizes, window geometry and panel visibility through QSettings, plus View → Reset Workspace Layout.
- Adds QET source-symbol preview rotation, placement with preview orientation, diagram rotation controls (`Ctrl+R`, `Ctrl+Shift+R`), context-menu actions, drag/snap-to-hotspot, Delete and undo/redo.
- Persists drawing-only symbol instances and rotations in the JSON diagram document, independently from the electrical network topology.
- Keeps QET source assets labelled as unverified drawing candidates; they are not silently promoted into electrical equipment or included in the authoritative SLD SVG export.
- Adds a portable Windows x64 PyInstaller `onedir` ZIP build, Windows release workflow, GitHub Pages download page and distribution documentation.
- Adds an offscreen Qt acceptance smoke test for splitter visibility/resizing, source catalogue loading, rotation, placement, undo/redo and JSON persistence.

## Validation performed in the build container

- `python -m compileall -q src tests scripts`: PASS.
- `python -m pytest`: **555 passed, 3 skipped**. The three Qt-specific tests were skipped because PySide6 is not installed in the build container.
- AST parse: 310 Python files PASS.
- `git diff --check`: PASS.
- Ruff and live Qt/Windows smoke: NOT RUN in the build container; must be executed in the user's Windows/PySide6 environment.

## Windows acceptance commands

```powershell
ruff check src tests scripts
ruff format --check src tests scripts
python -m compileall -q src tests scripts
python -m pytest
.\scripts\verify_app_reboot_004.ps1
python -m power_fault_analyzer.interfaces.desktop.app
```

## Distribution gate

The root `LICENSE` in the inspected working tree is empty. `scripts/build_windows_release.ps1` deliberately refuses to produce a public binary until the project license is selected and Qt/PySide6 redistribution obligations have been reviewed. The website also requires the exact public GitHub owner/repository slug in `website/index.html` and GitHub Pages configuration. Therefore this increment provides a release pipeline and website source, not a live hosted website or a published executable.

The ZIP is a portable folder distribution, not an MSI installer. It includes an executable and runtime dependencies after a successful Windows build.

## Application-scope caveat

Rotation and placement added here apply to pinned QElectroTech **drawing-only candidates**. They do not create electrical equipment, terminals or network connections. The physical SLD symbols for domain equipment still require explicit symbol-to-equipment mapping and engineering review in a subsequent increment.
