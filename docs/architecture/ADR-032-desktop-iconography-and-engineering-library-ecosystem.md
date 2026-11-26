# ADR-032 — Desktop iconography and engineering library ecosystem

- Status: Accepted for implementation baseline
- Date: 2026-11-24

## Context

The engineering workbench must be maintainable as an open-source engineering application. It needs consistent iconography, vector electrical symbols, scientific plotting, and clearly separated optional CAD and 3D capabilities. Visual assets must not be confused with electrical-domain equipment or normative certification.

## Decisions

1. Use QtAwesome as the desktop icon adapter, with native Qt standard-icon fallbacks for offline/minimal environments.
2. Use the pinned QElectroTech Elements candidate set as an upstream symbol source. Keep source commit, asset path, hashes and CC BY attribution. Do not promote a candidate to a normative IEC symbol without a documented crosswalk.
3. Keep SVG/QET artwork in the presentation layer. A drawing symbol cannot create terminals, connections or network topology implicitly.
4. Retain PyQtGraph for interactive scientific plots and Matplotlib for static/report graphics.
5. Expose ezdxf and PyVista/VTK/trimesh as optional extras only. Their dependencies do not imply that DXF semantic round-trip or 3D engineering workflows are complete.
6. Keep NumPy, SciPy, NetworkX, Pint and pandas as the numerical, graph and engineering-data foundation already present in the project.
7. Persist busbar diagram orientation as presentation metadata in network document schema 1.4. It must not alter the physical network or electrical calculations. Schemas 1.0–1.3 remain readable.
8. Use pytest-qt for GUI-level automated tests; preserve offscreen smoke tests for desktop lifecycle and workflow checks.

## Consequences

- Toolbars, equipment palette, project explorer, source-symbol browser and workspace tabs share a consistent icon source.
- Busbar rotation is undoable and persisted; electrical connectivity remains bound to explicit terminals and buses.
- Optional CAD and 3D features must be delivered through dedicated adapters and validation suites before being advertised as implemented.
- Release engineering must generate an SBOM and ship exact third-party notices. Qt, Font Awesome, QElectroTech and optional VTK licensing must be reviewed for the exact distributed artifacts.
- The repository's project-level `LICENSE` remains an owner decision; dependency licenses do not select the license for PFA itself.
