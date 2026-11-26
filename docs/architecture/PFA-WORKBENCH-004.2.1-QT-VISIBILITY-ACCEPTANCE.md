# PFA-WORKBENCH-004.2.1 — Qt visibility acceptance correction

## Cause

The 004.2 Windows acceptance script constructed `WorkbenchWindow` but never
showed the top-level window. Qt's `QWidget.isVisible()` is false whenever any
ancestor, including the top-level `QMainWindow`, has not been shown. The failure
therefore measured harness visibility rather than whether the property editor
was revealed by selection.

## Correction

- The offscreen acceptance harness now calls `window.show()` and processes Qt
  events before checking child visibility.
- Selecting a diagram object explicitly reveals `inspector_tabs` and
  `properties_panel`, then selects the Properties tab.
- The acceptance checks top-level window, inspector tabs, properties panel and
  property editor visibility after selection.
- The existing domain preflight, atomic command, QUndoStack undo/redo, implicit
  layout restoration, equipment label-following and topology-preservation checks
  remain unchanged.

## Verification boundary

The source/build container does not include PySide6. `compileall` and the full
non-Qt pytest suite are executed there; the dedicated offscreen Qt acceptance
script runs from the user's Windows virtual environment during installation.
