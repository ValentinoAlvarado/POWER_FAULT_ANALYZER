# Desktop distribution and public releases

POWER_FAULT_ANALYZER is a native Windows x64 desktop engineering application. The public website in `website/` is the download and documentation front door.

## License

PFA original code is released under **GPL-3.0-or-later**. Third-party dependencies and assets retain independent licenses. The combined PySide6 Community Edition application selects the GPLv3-compatible licensing route. QElectroTech Elements remain CC BY 3.0. See `LICENSE`, `NOTICE.md`, `LICENSES/` and `docs/engineering/THIRD_PARTY_LICENSE_REGISTER.md`.

## Windows release assets

Each successful tagged Windows workflow publishes:

- `PFA-Setup-x64.exe`: per-user Windows installer built with NSIS; no administrator elevation is required.
- `PFA-Windows-x64.zip`: portable PyInstaller onedir distribution.
- `SHA256SUMS.txt`: SHA-256 checksums for all principal release assets.
- `SBOM.cdx.json`: CycloneDX 1.6 inventory of Python distributions resolved in the release build environment.
- `PYTHON-DEPENDENCY-LICENSES.md`: license metadata for the exact build environment; `NOASSERTION` entries require review.
- `THIRD_PARTY_NOTICES.md` and `BUILD-INFO.json`.

Python 3.13 x64 is the release toolchain. The release workflow acquires the pinned QElectroTech seed, runs the complete test/Qt acceptance gate, builds the standalone application with PyInstaller, then compiles the setup executable with NSIS using the zlib compressor.

## Publish the repository and website

Run `PUBLISH_TO_GITHUB.ps1` from the repository root after installing Git for Windows and GitHub CLI and authenticating with `gh auth login`. It creates the public repository `ValentinoAlvarado/POWER_FAULT_ANALYZER`, pushes `main`, sets repository metadata and attempts to enable Pages for GitHub Actions. If Pages cannot be enabled by API, set **Settings → Pages → Build and deployment → Source → GitHub Actions**.

Website: `https://valentinoalvarado.github.io/POWER_FAULT_ANALYZER/`. The download button activates only when a published release contains `PFA-Setup-x64.exe` and `SHA256SUMS.txt`.

## First preview release

After the initial `main` push and Pages deployment succeed, create and push a preview tag:

```powershell
git tag -a v0.1.0-beta.1 -m "POWER_FAULT_ANALYZER preview release"
git push origin v0.1.0-beta.1
```

The tag starts `.github/workflows/windows-release.yml`. The workflow creates a GitHub prerelease only if the Windows build and acceptance gates succeed. The download page detects the resulting installer automatically.

## Signing and SmartScreen

The first installer is unsigned. Windows may show an unknown-publisher or SmartScreen warning. Do not claim a signed publisher or SmartScreen reputation until a code-signing certificate and protected signing workflow are configured.

## Engineering scope

The public page and release notes must preserve the limits described in `docs/product/PFA_PRODUCT_READINESS_2026-11-25.md`: no full IEC 60909 compliance, AC/DC load flow, OPF, N-1 studies or complete end-to-end support for every equipment category is claimed.
