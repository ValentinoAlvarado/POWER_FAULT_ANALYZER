# PFA-UX-001 — Engineering Workbench Design System

## Status

First implementation baseline. This document defines the visual shell and its constraints; it does not claim that the complete PFA 2.0 interaction model is implemented.

## Product direction

- Theme: dark technical shell.
- Organization: hybrid, retaining conventional menus and using one compact contextual command bar.
- Density: professional; prioritize legibility and predictable grouping over maximum control count.
- Reference principles: document-centric workflows, persistent project navigation, contextual commands, property inspection and dockable panels. The UI is inspired by engineering CAD applications but is not a clone of any product.

## Visual architecture

The desktop window is organized into:

1. Main menu for stable application-wide commands.
2. Compact command bar, grouped into Project, Network, Diagram, and Study & Export.
3. Project Explorer and equipment palette on the left.
4. Central document workspace with network canvas and results.
5. Properties and source-library inspector on the right.
6. Collapsible calculation console and messages at the bottom.
7. Status information for study base and model context.

Dock widgets remain movable, floatable and closable. Workspace geometry and panel state are persisted through QSettings and are kept separate from project/network data.

## Theme tokens

The semantic palette is implemented in
`src/power_fault_analyzer/interfaces/desktop/workbench/design_system.py`.

The dark palette defines application, panel, input, divider, text, accent, selection,
status and canvas-grid colors. The light palette remains available as a user preference.
All widget styles are produced from one stylesheet function rather than duplicated
light/dark fragments inside the main window.

The dark application shell deliberately keeps the SLD canvas on a neutral light
engineering-paper surface in this increment. Existing electrical symbols and imported
drawing primitives were designed primarily for a light drawing surface. Switching the
canvas to dark before migrating every renderer, label, junction, route and export style
would reduce contrast or hide engineering geometry. A dark SLD canvas is therefore
deferred until renderer-wide theme support has separate visual acceptance.

## Typography and density

- Interface family: Segoe UI.
- Base interface size: 10 pt.
- Diagram annotations use a technical sans-serif family and enlarged nominal labels.
- Data values should use aligned numeric formatting; a monospaced data font is reserved
  for future result blocks and coordinate readouts.
- Command bar labels remain short; full descriptions belong in tooltips.

## Engineering display rules

- Nominal bus voltage is a model attribute and remains available in the basic diagram profile.
- Operating voltage, fault current, per-unit values and other result quantities appear only
  when a compatible study has produced them.
- Incomplete or unresolved parameters must remain visibly identified.
- An imported QElectroTech drawing candidate is not automatically an electrical equipment
  object or an IEC-verified symbol.
- Theme changes must not alter the electrical model, topology, diagram coordinates,
  solver behavior or exported numerical values.

## Current implementation scope

Implemented in this increment:

- Centralized semantic color palettes and Qt stylesheet generation.
- Dark theme as the default, with the preference persisted in QSettings.
- Light theme retained as a user-selectable alternative.
- Theme-aware canvas background and grid colors.
- Theme-aware QtAwesome icon color at initial widget construction.
- Labeled hybrid command bar groups.
- Regression tests for palette selection and stylesheet token resolution.

Not claimed by this increment:

- Full command palette / command search.
- Complete contextual ribbon or workspace switcher.
- Theme-aware recoloring of every electrical graphics primitive.
- Configurable layer manager or per-object display blocks.
- Final high-density/low-density scaling policy.
- Full visual acceptance at all Windows DPI settings.

## Acceptance gates

1. Full pytest suite remains green.
2. Workbench constructs in dark and light themes.
3. Theme preference survives application restart.
4. Menus, toolbars, dock titles, inspectors, controls and status bar remain readable.
5. SLD symbols, conductors, junctions and annotations retain contrast.
6. Theme changes do not mutate network objects, diagram metadata or study results.
7. Visual review is performed at 1366x768 and 1920x1080, with Windows scaling at 100%, 125% and 150%.

The next increment should address workspace/panel persistence and a real command context
before attempting a full SLD renderer theme.
