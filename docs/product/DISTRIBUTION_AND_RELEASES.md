# Desktop distribution and public releases

POWER_FAULT_ANALYZER is a native Windows x64 desktop engineering application. The public website in `website/` is the download and documentation front door; it does not replace the native editor.

## License and notices

PFA original source code is licensed under **GPL-3.0-or-later**. Third-party dependencies, symbols, fonts and bundled assets retain their independent licenses. The PySide6 Community Edition distribution follows the GPL-compatible route documented in `NOTICE.md`. QElectroTech Elements retain their separate CC BY 3.0 terms. See `LICENSE`, `NOTICE.md`, `LICENSES/` and `docs/engineering/THIRD_PARTY_LICENSE_REGISTER.md`.

The release package includes the root project license, third-party license texts, notices, a CycloneDX SBOM, a Python dependency-license inventory, build metadata and SHA-256 checksums. The build-specific dependency inventory is authoritative for that exact build environment. A tagged release is blocked when a package is reported with unknown/NOASSERTION license metadata and the exact package version lacks a completed human review record in `RELEASE_LICENSE_REVIEW.csv`. Do not guess, auto-approve or copy review records across package versions.

## Windows distribution contract

The active GitHub Actions workflow targets Windows x64 with Python 3.13 and creates one portable distribution:

- `PFA-Windows-x64.zip`: portable PyInstaller `onedir` application. Extract the archive and launch `POWER_FAULT_ANALYZER.exe`.
- `SHA256SUMS.txt`: SHA-256 checksums for the ZIP and release sidecars.
- `SBOM.cdx.json`: CycloneDX 1.6 inventory of Python distributions in the release build environment.
- `PYTHON-DEPENDENCY-LICENSES.md`: license metadata for the exact release environment; unresolved entries require human review before a tagged release.
- `THIRD_PARTY_NOTICES.md`: third-party attribution and license register.
- `BUILD-INFO.json`: version, Python architecture, source commit, build timestamp and distribution description.

**This workflow does not build an NSIS installer or MSI executable.** `installer/PFA-Setup-x64.nsi` is retained in the repository but is not part of the active portable-ZIP pipeline.

## Workflow behavior and acceptance boundary

The workflow has two trigger paths:

- **Manual `workflow_dispatch`:** builds and uploads the portable artifacts as a GitHub Actions workflow artifact. It does not publish a GitHub Release.
- **Tag push matching `v*`:** builds the same artifacts, executes the dependency-license review gate and publishes a GitHub Release with the six assets when every required step succeeds.

The Windows runner performs pinned QElectroTech asset acquisition, Cairo runtime setup, Ruff lint, compilation, the complete pytest suite, APP-REBOOT-005 offscreen workbench/QElectroTech acceptance, PyInstaller packaging, a frozen-executable startup smoke, SBOM/license inventory generation and checksum verification. A repository-wide Ruff formatter gate is deliberately deferred: the current audit reports 56 existing files requiring a separate style-only migration, which should not be mixed into a release/build repair.

The offscreen acceptance exercises selected workbench layout, drawing-symbol preview/placement, rotation, drag, undo/redo and persistence behavior. The frozen-executable smoke launches the packaged process with Qt offscreen and confirms that it remains alive for six seconds. These checks do **not** replace interactive testing on a normal Windows desktop, a clean-machine extraction/launch, inspection of the rendered diagrams or independent electrical benchmark validation.

A configured workflow is not proof of a successful build. A workflow artifact is not yet a public release. The build must complete successfully, the downloaded ZIP and sidecars must be inspected, and the executable must be extracted and exercised on a clean Windows x64 environment before the product is described as release-accepted. Retain the run URL, artifact identity, SHA-256 values and acceptance record.

## Portable update without reinstalling

The desktop GUI checks the public GitHub Releases feed at startup (enabled by default) and also exposes **Help → Check for Updates…**. The preference can be disabled from the same Help menu. The check sends only an unauthenticated request for public release metadata; it does not upload project data, documents, telemetry or machine identifiers.

Only a published GitHub Release with all three required assets is considered an update. Temporary GitHub Actions workflow artifacts are intentionally excluded. A tagged release must publish these user-facing and updater assets:

- `PFA-Setup-x64.exe`: per-user Windows installer for first-time installation
- `PFA-Windows-x64.zip`: onedir payload used by the in-app updater (also usable as a portable distribution)
- `SHA256SUMS.txt`: checksums for the installer, update payload and release sidecars
- `Update-PFA-Portable.ps1`: verified in-place updater invoked by the desktop application

When a newer version is found, PFA asks the user before downloading anything. After consent, it saves a dirty project, downloads the three assets in the background, verifies both the ZIP and PowerShell updater against the same SHA-256 manifest, and launches the updater in a hidden PowerShell process. PFA then closes so Windows can replace the portable application directory in place. The updater waits for the GUI process to exit, stages and validates the onedir archive, retains the previous application as a uniquely named backup, promotes the new files and restarts PFA. A promotion failure restores the prior application and attempts to restart it. Temporary download files are scheduled for cleanup after the updater exits.

The update does not run an uninstall/reinstall wizard and does not replace the user's project directory or Qt preferences. New Save/Open dialogs default to Documents/POWER_FAULT_ANALYZER/Projects. When an older installation contains .pfa project documents, the updater copies those documents and their .pfa.network.json sidecars into that Documents folder before promoting the new application; name collisions are renamed rather than overwritten. The old application backup is retained as a second recovery path. Keep the generated application.backup-* directory until the new version and representative workflows have been accepted.

A portable build downloaded directly from a GitHub Actions artifact can be tested manually, but it does not become discoverable to the in-app checker until a complete version is published as a GitHub Release. Publishing the first release still requires the tag-triggered dependency-license review gate and the usual release acceptance checks.

## Public download page

The website reads the newest published GitHub Release that contains `PFA-Setup-x64.exe` (including a published prerelease) and activates the Windows install link only for that verified asset. The installer is a per-user NSIS setup executable and does not require Python or PyCharm. The portable ZIP remains available as the in-app update payload and an alternative portable distribution. In the absence of a complete release, the website displays that no verified installer is available. The website does not itself build, sign or validate the executable.

## Release gates

Before publishing a tag:

1. Confirm the source branch and commit intended for release.
2. Run and retain the successful Windows release workflow.
3. Review `PYTHON-DEPENDENCY-LICENSES.md` generated by that exact build. Complete `RELEASE_LICENSE_REVIEW.csv` for each exact package/version reported with unknown/NOASSERTION metadata.
4. Download and inspect all six artifacts; verify every SHA-256 entry.
5. Install the NSIS setup executable on a clean Windows x64 environment, then perform representative create/validate/calculate/save/reopen/export workflows. Also extract and run the portable ZIP independently.
6. Confirm the release notes preserve the product limitations and identify the binary's signing status.

The binary is unsigned unless a protected code-signing certificate and signing workflow are separately configured. Do not claim SmartScreen reputation or a signed publisher in release notes.

## Product scope

Release notes and the public website must preserve the limitations described in `docs/product/PFA_PRODUCT_READINESS_2026-11-25.md` and the evidence requirements in `docs/validation_protocol.md`. Passing automated tests does not establish IEC certification, universal equipment support, independent electrical validation or suitability as the sole basis for safety-critical operational decisions.
