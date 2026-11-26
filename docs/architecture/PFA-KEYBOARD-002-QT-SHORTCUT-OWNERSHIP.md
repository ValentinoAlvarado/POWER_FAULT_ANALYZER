# PFA-KEYBOARD-002 — Qt Shortcut Ownership and Focus

## Decision

POWER_FAULT_ANALYZER continues to use the native Qt 6 / PySide6 command stack:

- `QAction` is the command surface shared by menus and the command bar.
- `QKeySequence` expresses key sequences.
- `Qt.WidgetWithChildrenShortcut` scopes diagram-editing actions to the canvas and descendants.
- `QUndoStack` is the undo/redo implementation.
- `QGraphicsView` / `QGraphicsScene` are the diagram interaction surface.

No third-party hotkey manager and no custom global keyboard dispatcher are introduced.

## Defect corrected

Several actions (`Delete`, rotate, fit, grid and snap) were initially created by the main-window `_action()` helper before `NetworkCanvasView` existed. Later code called `canvas.addAction(action)` and assigned `WidgetWithChildrenShortcut`, but adding an action to a widget does **not** change its QObject parent. The QAction parent remained `WorkbenchWindow`, so Qt resolved the shortcut scope against the main window rather than the canvas. This made canvas-only shortcuts leak into unrelated controls and behave inconsistently with actions created directly with the canvas as parent.

The actions are now explicitly reparented to `NetworkCanvasView` before setting their shortcut context. Their menu associations remain intact; the QAction is still the single command source for menu and keyboard activation.

## Focus behavior

`NetworkCanvasView` and its viewport explicitly use `Qt.StrongFocus`. A left/right mouse press gives focus to the view before the scene handles selection. This gives `WidgetWithChildrenShortcut` a deterministic focus scope on Windows.

Text editors remain outside the canvas widget hierarchy. Their native editing shortcuts are not intercepted by canvas actions.

## Verification changes

The Windows/offscreen verifier checks:

1. QAction QObject parent and shortcut context.
2. Main-window ownership of file actions.
3. Actual `QTest.keyClick` events for G, Ctrl+G, Ctrl+R, Ctrl+Shift+R, arrows, Ctrl+Z, Ctrl+Y, Delete, Ctrl+A and Escape.
4. Canvas commands do not execute when a property `QLineEdit` has focus.
5. Rotation and grid/snap changes update the actual workspace and remain undoable.

The previous verifier called `_toggle_grid()` and `_toggle_snap()` directly, which proved the Python methods but did not prove that keyboard events reached them. Those false-positive checks have been replaced with real Qt key events.

## User-facing scope

- File shortcuts (`Ctrl+N/O/S`, `Ctrl+Shift+S`) remain window-scoped.
- Diagram editing shortcuts are canvas-scoped.
- `Ctrl+Z` / `Ctrl+Y` use the Workbench `QUndoStack` while the canvas has focus. Text fields and Code & Automation retain their own local text-edit undo behavior.
- Arrow nudging requires a selected movable diagram object.
- Rotation currently supports busbars and drawing-only symbols. Functional electrical equipment is not rotated by the generic shortcut unless its model and terminal geometry explicitly support such a transformation.
