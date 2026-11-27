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

The portable updater is an external PowerShell script. It does not run inside the GUI. Download these three files from the same successful workflow artifact:

- `PFA-Windows-x64.zip`
- `SHA256SUMS.txt`
- `Update-PFA-Portable.ps1`

Close PFA before updating. Verify that project files are stored outside the application directory. Run the updater from PowerShell 5.1 or later:

```powershell
& .\Update-PFA-Portable.ps1 `
    -ZipPath "C:\Downloads\PFA-Windows-x64.zip" `
    -ChecksumPath "C:\Downloads\SHA256SUMS.txt" `
    -InstallDirectory "C:\PFA_ACCEPTANCE_RUN18\application"
```

The updater checks the ZIP SHA-256 against the downloaded manifest before touching the current installation. It stages and inspects the onedir package, checks product/architecture/build metadata, detects a running executable, retains the previous application in a uniquely named backup directory, and attempts rollback if promotion fails. It writes an update record beside the installation. Do not delete the backup until the updated executable and representative project workflows have been accepted.

Qt workbench geometry, panel state and theme are persisted separately through `QSettings`; the replacement script does not modify those preferences. Project documents should remain in a user-owned location such as `Documents\POWER_FAULT_ANALYZER\Projects\`, never inside the portable application directory.

## Public download page

The website reads the repository's latest GitHub Release and activates the Windows download link only when that release contains `PFA-Windows-x64.zip`. In the absence of such a release, it displays that no verified release is available. The website does not itself build, sign or validate the executable.

## Release gates

Before publishing a tag:

1. Confirm the source branch and commit intended for release.
2. Run and retain the successful Windows release workflow.
3. Review `PYTHON-DEPENDENCY-LICENSES.md` generated by that exact build. Complete `RELEASE_LICENSE_REVIEW.csv` for each exact package/version reported with unknown/NOASSERTION metadata.
4. Download and inspect all six artifacts; verify every SHA-256 entry.
5. Extract and run the ZIP on a clean Windows x64 environment, then perform representative create/validate/calculate/save/reopen/export workflows.
6. Confirm the release notes preserve the product limitations and identify the binary's signing status.

The binary is unsigned unless a protected code-signing certificate and signing workflow are separately configured. Do not claim SmartScreen reputation or a signed publisher in release notes.

## Product scope

Release notes and the public website must preserve the limitations described in `docs/product/PFA_PRODUCT_READINESS_2026-11-25.md` and the evidence requirements in `docs/validation_protocol.md`. Passing automated tests does not establish IEC certification, universal equipment support, independent electrical validation or suitability as the sole basis for safety-critical operational decisions.
