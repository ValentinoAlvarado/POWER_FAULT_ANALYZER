# PFA-KEYBOARD-001 — Workbench Keyboard Shortcuts

This increment adds keyboard commands to the existing PySide6 Engineering Workbench. The Qt QAction parent/shortcut scope and canvas focus behavior are corrected by PFA-KEYBOARD-002.
Canvas editing shortcuts use `Qt.WidgetWithChildrenShortcut` with `NetworkCanvasView` as the QAction QObject parent. The view and viewport accept strong focus, and a click on the canvas gives it focus. These shortcuts do not intercept the Project Explorer, property fields, or Code & Automation widgets.

## File

| Shortcut | Command |
|---|---|
| Ctrl+N | New project |
| Ctrl+O | Open project |
| Ctrl+S | Save project and network sidecar |
| Ctrl+Shift+S | Save As |

## Edit (diagram canvas focus)

| Shortcut | Command |
|---|---|
| Ctrl+Z | Undo |
| Ctrl+Y or Ctrl+Shift+Z | Redo |
| Ctrl+A | Select visible buses, equipment and drawing symbols |
| Delete or Backspace | Delete selection as an atomic, undoable workspace command |
| Escape | Clear selection |

## Diagram (diagram canvas focus)

| Shortcut | Command |
|---|---|
| Arrow keys | Nudge selection one grid step when snap is enabled; otherwise one scene unit |
| Shift+Arrow | Nudge five grid steps when snap is enabled; otherwise ten scene units |
| Ctrl+R / Ctrl+Shift+R | Rotate selected compatible diagram object clockwise/counterclockwise |
| Ctrl++ / Ctrl+= | Zoom in |
| Ctrl+- | Zoom out |
| Home or Ctrl+0 | Fit diagram |
| G | Show/hide grid |
| Ctrl+G | Toggle snap to grid |
| F2 | Focus selected element Properties inspector |

## Analysis and export

| Shortcut | Command |
|---|---|
| F5 | Run fault study |
| Ctrl+E | Export active report |
| Ctrl+Shift+E | Export one-line diagram as SVG |
| F1 | Show keyboard shortcut reference |

Undo/redo operates on changes represented on the Workbench `QUndoStack`. This includes
canvas moves/nudges, rotation, drawing-symbol insertion/removal, and property-editor
transactions. Domain operations that are not yet represented as `QUndoCommand` remain
outside that history and are not silently described as undoable.

The Delete-selection command snapshots and restores `NetworkWorkspace` in place, preserving
the `NetworkWorkspace` and `Network` aggregate object identities while retaining stable
bus/equipment UUIDs and terminal connections. Multi-delete is preflighted against a deep
copy and committed atomically.
