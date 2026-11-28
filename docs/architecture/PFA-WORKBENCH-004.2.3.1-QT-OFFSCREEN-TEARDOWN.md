# PFA-WORKBENCH-004.2.3.1 — Qt Offscreen Acceptance Teardown

## Defect

The property-editor acceptance script creates an in-memory `WorkbenchWindow`,
then edits the synthetic workspace through the real inspector and QUndoStack.
Those edits mark the window dirty. Calling `window.close()` then enters the
production `closeEvent`, which correctly asks the user to Save/Discard/Cancel.
In the offscreen Qt platform there is no interactive user to answer the modal
`QMessageBox`, so the test process appears to hang after the last property-editor
assertion. The Qt message `This plugin does not support propagateSizeHints()`
was emitted by that modal dialog; it was not the root error.

## Correction

Immediately before teardown, the acceptance harness marks its synthetic
in-memory workspace clean (`window._dirty = False`), calls `window.close()`,
processes Qt events, and asserts that the top-level window is no longer visible.
This preserves the production unsaved-project prompt for actual users and avoids
weakening the property-editor assertions.

## Scope

Test-harness teardown only. No electrical model, diagram geometry, inspector
transaction, command bus, or production close-event behavior is changed.
