# Notices and redistribution terms

## POWER_FAULT_ANALYZER

Unless a file or bundled component says otherwise, the original PFA source code is
licensed under **GNU GPL-3.0-or-later**. Copyright (C) 2026 Valentino Alvarado and
contributors. See [`LICENSE`](LICENSE).

The GPL applies to PFA's original code. Third-party dependencies, symbols, fonts,
icons and other assets retain their own licenses and attribution requirements.
They are not relicensed by the PFA project license.

## Qt for Python / PySide6

PFA's desktop build uses the **Community Edition** of Qt for Python (PySide6 and
Shiboken6). Qt for Python Community Edition is available under LGPLv3/GPLv3 or a
Qt commercial license. This PFA distribution selects the GPLv3-compatible route
for the combined PFA application. Qt modules and other third-party components
retain their own notices. See the Qt licensing documentation:

- https://doc.qt.io/qtforpython-6/commercial/index.html
- https://doc.qt.io/qt-6/licensing.html

A binary release must include this notice, the corresponding source code, and the
license texts/notices for the exact shipped Qt modules. Do not remove or replace
Qt copyright notices. Commercial Qt use is a separate licensing path.

## QElectroTech Elements

Selected, unmodified source elements are acquired from the pinned QElectroTech
Elements repository commit recorded in `assets/third_party/qelectrotech-elements/`.
They are attributed to **The QElectroTech team** and remain under **CC BY 3.0**.
The original `ELEMENTS.LICENSE`, asset manifest, source paths and hashes are kept
with the assets. These files are not relicensed under the PFA GPL license.

Source: https://github.com/qelectrotech/qelectrotech-elements
License: https://creativecommons.org/licenses/by/3.0/

## Python and other runtime dependencies

The exact Python package inventory and license metadata used for each Windows
build are generated as `PYTHON-DEPENDENCY-LICENSES.md` and `SBOM.cdx.json` and are
included with the release assets and installed application. The source-level
register is `docs/engineering/THIRD_PARTY_LICENSE_REGISTER.md`.

## NSIS installer

The Windows setup executable is produced with NSIS using its zlib compressor.
NSIS's zlib/libpng license notice is included in `LICENSES/NSIS-zlib-libpng.txt`.

## No blanket relicensing

No PFA notice changes the license of an external library, icon pack, font, or
symbol source. If a release build adds a new dependency or asset, update the
third-party register and release notices before publication.
