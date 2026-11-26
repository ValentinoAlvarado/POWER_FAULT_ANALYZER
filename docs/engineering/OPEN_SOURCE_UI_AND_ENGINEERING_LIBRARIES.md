# Open-source UI and engineering library integration

## Adopted in the desktop baseline

| Library | License | Role | Integration status |
|---|---|---|---|
| QtAwesome | MIT (library); icon packs retain their own licenses | Consistent toolbar, menu, palette and inspector iconography | Required desktop dependency; native Qt fallback remains available |
| Qt for Python / PySide6 QtSvg | Qt LGPL/GPL/commercial terms | Native widgets and SVG rendering | Existing desktop foundation |
| QElectroTech Elements | CC BY 3.0 | Source electrical symbol candidates | Existing pinned manifest, hash-verifying acquisition script and provenance-aware importer |
| PyQtGraph | MIT | Interactive scientific curves and signal plots | Existing desktop dependency and results-workspace foundation |
| Matplotlib | PSF-based license | Static plots and report graphics | Existing desktop dependency |
| NumPy / SciPy | BSD-3-Clause | Numerical arrays and scientific algorithms | Existing core dependencies |
| NetworkX | BSD-3-Clause | Graph algorithms and topology utilities | Existing core dependency |
| Pint | BSD-3-Clause | Engineering units and conversions | Existing core dependency |
| ezdxf | MIT | DXF import/export adapter | Optional `cad` extra; not yet wired to project document commands |
| PyVista / VTK | MIT / BSD-3-Clause (verify exact VTK notices at release) | Optional 3D scene and mesh visualization | Optional `visualization3d` extra; no 3D engineering workflow claimed |
| trimesh | MIT | Mesh interchange and preprocessing | Optional `visualization3d` extra |

## Install profiles

- Desktop + reports: `python -m pip install -e ".[dev,desktop,reports]"`
- CAD interchange development: `python -m pip install -e ".[dev,desktop,reports,cad]"`
- 3D visualization development: `python -m pip install -e ".[dev,desktop,reports,visualization3d]"`
- Full optional engineering workstation: `python -m pip install -e ".[dev,desktop,reports,cad,visualization3d,api,notebook]"`

## Symbol asset acquisition and normative status

Run `scripts/Acquire-QElectroTechSymbolSeed.ps1` from the repository root on Windows PowerShell 5.1. It downloads the curated original QElectroTech files from the pinned upstream commit, verifies Git blob SHA-1 values, and stores SHA-256 inventory and the original `ELEMENTS.LICENSE`. The repository intentionally does not silently replace missing source artwork with hand-drawn approximations.

Every QET element remains a source candidate until its exact intended use, terminal mapping and normative cross-reference have been verified. A QET folder name is not evidence of IEC 60617 conformity. Source symbols remain drawing-only unless an explicit domain equipment and terminal mapping exists.

## Distribution obligations

Keep third-party code dependencies distinct from third-party artwork. Generate an SBOM from the exact release environment, preserve all upstream notices, audit transitive dependencies, and review Qt LGPL obligations for the chosen distribution model. Do not bundle the complete QET library without satisfying its attribution requirements. QET Elements must not be used as machine-learning training data under its stated license restrictions.

## Deferred, not silently claimed

The `cad` and `visualization3d` extras provide dependency foundations only. They do not claim that DXF round-trip engineering semantics, 3D equipment models, BIM, or 3D electrical analysis are already implemented. Each needs a separate adapter, data contract, validation suite and user workflow.
