# Third-party attribution and license register — initial seed

## QElectroTech Elements collection

- **Work:** QElectroTech official Elements collection, curated files under `10_electric/91_en_60617/`.
- **Author/attribution:** The QElectroTech team.
- **Repository:** https://github.com/qelectrotech/qelectrotech-elements
- **Pinned commit:** `661f5e9ce5caa76277cafd3ebf0e0320fc4af229`.
- **License:** Creative Commons Attribution 3.0 (CC BY 3.0), as stated in the pinned `ELEMENTS.LICENSE`.
- **License text:** https://creativecommons.org/licenses/by/3.0/
- **Source notice:** https://github.com/qelectrotech/qelectrotech-elements/blob/661f5e9ce5caa76277cafd3ebf0e0320fc4af229/ELEMENTS.LICENSE
- **Use:** selected original `.elmt` files are candidates for integration into PFA electrical diagrams. Preserve each file's original author/information, source path and hash. If redistributing the element collection or portions outside a diagram, meet CC BY attribution conditions.
- **Restrictions/notes:** the collection is provided without warranty; its license explicitly disallows use of the files as sample data for building machine-learning models. PFA will not use this symbol collection for ML training.
- **Modifications:** none are made by the acquisition script. If future modifications are made, mark the affected files as modified and preserve source-to-derivative traceability.

## Qt for Python / PySide6

- **Project:** Qt for Python (PySide6 and Shiboken6).
- **License model:** LGPLv3/GPLv3 or Qt Commercial Edition, as documented by Qt.
- **Documentation:** https://doc.qt.io/qtforpython-6/commercial/index.html
- **Distribution note:** a proprietary PFA release using the Community Edition must meet all applicable LGPLv3 obligations and audit each Qt module used; the Qt commercial distribution is a separate option. Do not assume the current development install alone resolves product distribution obligations.

## Other dependencies

Maintain a generated SBOM and the licenses/notices for the exact pinned versions of pandas, NumPy, SciPy, NetworkX, Pydantic, Pint, PyQtGraph, ReportLab and openpyxl. Their presence in the current development environment is not a blanket approval of every transitive dependency for product packaging.


## Desktop and optional engineering libraries

- **QtAwesome** — MIT; Font Awesome icon packs are separately licensed. Used for application command and palette iconography.
- **PyQtGraph** — MIT; interactive scientific plotting.
- **Matplotlib** — Matplotlib license (PSF-based); static scientific/report plots.
- **ezdxf** — MIT; optional DXF interchange dependency (`cad` extra), not yet an implemented project-document round trip.
- **PyVista** — MIT; optional 3D visualization frontend (`visualization3d` extra).
- **VTK** — BSD-3-Clause; transitive 3D visualization runtime. Preserve exact upstream notices for the shipped version.
- **trimesh** — MIT; optional mesh interchange/preprocessing (`visualization3d` extra).

See `docs/engineering/OPEN_SOURCE_UI_AND_ENGINEERING_LIBRARIES.md` for install profiles, scope boundaries and distribution requirements. Release builds must generate a version-specific SBOM and include exact dependency notices.
- **Font Awesome Free icon assets (via QtAwesome)** — the QtAwesome Python wrapper is MIT; Font Awesome Free icons are CC BY 4.0 and its font files are SIL OFL 1.1. Preserve upstream attribution and font notices in binary distributions. Do not assume the wrapper's MIT license changes the icon/font licenses.
