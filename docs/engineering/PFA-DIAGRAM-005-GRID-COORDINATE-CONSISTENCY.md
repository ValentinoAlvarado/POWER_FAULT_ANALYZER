# PFA-DIAGRAM-005 — Grid and movement consistency

## Problem

The Qt Workbench previously applied different movement contracts to electrical
objects: bus symbols snapped to a hard-coded 20-scene-unit grid, while source,
canonical equipment and branch symbols moved continuously. Imported QET symbols
used the workspace grid, but were initialized through a separate path. The canvas
background also drew a hard-coded 20/100 grid. This produced mixed movement
sensitivity and made alignment unpredictable.

## Decision

The active `NetworkWorkspace.grid_spacing` is the single source of truth for the
visible fine grid and all movable electrical graphics objects:

- busbars and bus nodes;
- sources and synchronous generators;
- canonical equipment symbols (transformers, switching devices and generic items);
- two-terminal branch symbols;
- imported interactive QET symbols (which retain hotspot-based snapping);

When Snap is enabled, each object anchor is quantized using the same `snap_point()` function and workspace grid spacing. This includes mouse drags, keyboard nudges and QET hotspot placement. When Snap is disabled, all movable electrical graphics objects move continuously. Independent text
annotations remain independently movable and are not quantized; this allows fine
annotation placement without changing electrical symbol coordinates.

The major grid is five fine-grid intervals. A workspace grid-spacing change refreshes the background grid and every movable graphics item, including busbars, instead of leaving one item family on a stale or hard-coded spacing.

## Coordinate and persistence contract

- The snapping anchor for built-in electrical symbols is the item origin/center.
- QET imported symbols retain their declared hotspot as their snapping anchor.
- Programmatic position commands persist the actual accepted graphics position,
  not the unsnapped requested coordinate. Keyboard movement uses the same quantizer.
- On rendering, existing manual position overrides are normalized to the active
  grid when Snap is enabled. Automatically derived positions remain derived and
  are not converted into manual overrides.
- The physical `Network`, terminal connectivity, and equipment parameters are not
  changed by diagram movement.

## Verification

`test_network_canvas_grid_consistency.py` verifies that bus, source, canonical
asset and branch items use identical grid spacing, support a different configured
spacing, and all move continuously when Snap is disabled. These tests require
PySide6 and run on the desktop test environment; environments without PySide6
skip them. Existing QET hotspot tests remain the acceptance gate for imported
symbols.
