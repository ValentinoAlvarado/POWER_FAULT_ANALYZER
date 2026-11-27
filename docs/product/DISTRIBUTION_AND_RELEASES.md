# Desktop distribution and public releases

POWER_FAULT_ANALYZER is a native Windows x64 desktop engineering application. The public website in `website/` is the download and documentation front door.

## License and notices

PFA original source code is licensed under **GPL-3.0-or-later**. Third-party dependencies, symbols, fonts and bundled assets retain their independent licenses. The PySide6 Community Edition distribution is built on the GPL-compatible route. QElectroTech Elements retain their separate CC BY 3.0 terms. See `LICENSE`, `NOTICE.md`, `LICENSES/` and `docs/engineering/THIRD_PARTY_LICENSE_REGISTER.md`.

The release package includes the root project license, third-party license texts, notices, a CycloneDX SBOM, a Python dependency-license inventory, build metadata and SHA-256 checksums. A tagged release is blocked while packages with unknown license metadata lack explicit human review records in `RELEASE_LICENSE_REVIEW.csv`. Do not guess or automatically approve unknown package licenses.

## Windows distribution contract

The current GitHub Actions workflow produces one Windows x64 distribution:

- `PFA-Windows-x64.zip`: portable PyInstaller `onedir` application. Extract the archive and launch `POWER_FAULT_ANALYZER.exe`.
- `SHA256SUMS.txt`: SHA-256 checksums for the ZIP and release sidecars.
- `SBOM.cdx.json`: CycloneDX 1.6 inventory of Python distributions in the release build environment.
- `PYTHON-DEPENDENCY-LICENSES.md`: license metadata for the exact release environment; unresolved entries require review.
- `THIRD_PARTY_NOTICES.md`: third-party attribution and license register.
- `BUILD-INFO.json`: version, Python architecture, source commit and build timestamp.

**This workflow does not currently build or publish an NSIS installer executable.** `installer/PFA-Setup-x64.nsi` is retained in the repository but is not part of the active portable-ZIP pipeline. The website activates its download link only when a GitHub Release contains `PFA-Windows-x64.zip`.

## Release gates

The Windows workflow uses Python 3.13 x64, acquires the pinned QElectroTech symbol seed, configures the Cairo runtime, runs lint/compile/test and Qt acceptance gates, packages the standalone application, generates the SBOM and license inventory, and validates all checksums. For tagged releases, the dependency-license review gate must pass before the release is published.

The binary is unsigned unless a protected code-signing certificate and signing workflow are separately configured. Do not claim SmartScreen reputation or a signed publisher in release notes.

## Product scope

Release notes and the public website must preserve the limitations described in `docs/product/PFA_PRODUCT_READINESS_2026-11-25.md`. Passing automated tests does not establish IEC certification, universal equipment support, or suitability as the sole basis for safety-critical operational decisions.