# Public GitHub publication and Windows releases

## Target repository

- Owner: `ValentinoAlvarado`
- Repository: `POWER_FAULT_ANALYZER`
- Visibility: public
- License: GPL-3.0-or-later
- Website: `https://valentinoalvarado.github.io/POWER_FAULT_ANALYZER/`

The public handoff is a consolidated source snapshot. The original historical Git commit graph was not available in this handoff; the first push creates a new Git history and does not pretend to restore earlier commits.

## One-time repository publication

1. Extract the source handoff to a clean folder separate from the development checkout.
2. Install Git for Windows and GitHub CLI:
   ```powershell
   winget install --id Git.Git -e
   winget install --id GitHub.cli -e
   ```
3. Open PowerShell in the extracted project root and authenticate:
   ```powershell
   gh auth login
   gh auth status
   ```
4. Run:
   ```powershell
   Set-ExecutionPolicy -Scope Process Bypass -Force
   .\PUBLISH_TO_GITHUB.ps1
   ```

The script checks the authenticated account, refuses an existing remote repository or `origin`, creates `ValentinoAlvarado/POWER_FAULT_ANALYZER` as a public repository, pushes `main`, sets repository topics/homepage and attempts to enable GitHub Pages with GitHub Actions. It does not overwrite an existing repository.

If Pages configuration cannot be enabled automatically, use **Settings → Pages → Build and deployment → Source → GitHub Actions**. GitHub Pages publishes only `website/`; the page activates downloads only after it sees a published release containing both the Windows installer and checksums.

## First Windows build: inspect the artifact before publishing

After `main` exists, run the workflow manually from GitHub Actions:

- Workflow: **Windows desktop release**
- Branch: `main`
- Event: `workflow_dispatch`

The Windows runner installs Python 3.13 x64, NSIS and the pinned QElectroTech asset seed; runs the full Python and Qt acceptance suite; builds the PyInstaller onedir application; smoke-launches the frozen executable; creates the setup installer and portable ZIP; and uploads build artifacts.

Download the workflow artifact and inspect:

- `PYTHON-DEPENDENCY-LICENSES.md`
- `SBOM.cdx.json`
- `THIRD_PARTY_NOTICES.md`
- `SHA256SUMS.txt`
- `BUILD-INFO.json`

Some packages do not publish license metadata in their Python package metadata. The tagged-release workflow is deliberately blocked if any `NOASSERTION` package has not been reviewed. Verify each exact package/version against its upstream license and complete `RELEASE_LICENSE_REVIEW.csv` with the license, source URL, reviewer and notes. Do not guess. Commit and push the completed review register to `main` before tagging.

## First preview release

After the manual build is green and the license register is complete:

```powershell
git add RELEASE_LICENSE_REVIEW.csv
git commit -m "Review dependency licenses for Windows preview"
git push origin main

git tag -a v0.1.0-beta.1 -m "POWER_FAULT_ANALYZER preview release"
git push origin v0.1.0-beta.1
```

The tag triggers `windows-release.yml`. It repeats the complete acceptance and build, performs the dependency-license gate, and only then creates a GitHub prerelease with:

- `PFA-Setup-x64.exe`
- `PFA-Windows-x64.zip`
- `SHA256SUMS.txt`
- `SBOM.cdx.json`
- `PYTHON-DEPENDENCY-LICENSES.md`
- `THIRD_PARTY_NOTICES.md`
- `BUILD-INFO.json`

Once the GitHub Release is published, the website discovers the latest installer automatically. No release link is fabricated before the asset exists.

## Installer, signing and SmartScreen

The initial setup is a per-user NSIS installer using the zlib compressor. It creates Start Menu and desktop shortcuts and registers an uninstaller. The installer is unsigned. Windows may show an unknown-publisher or SmartScreen warning. Do not claim signed-publisher identity or SmartScreen reputation until a code-signing certificate and protected signing workflow are configured.

## License and third-party notices

PFA original code is GPL-3.0-or-later. PySide6 Community Edition is available under LGPLv3/GPLv3 or commercial terms; this combined GPL application selects the GPLv3-compatible route. QElectroTech elements remain CC BY 3.0. Third-party dependencies and symbols retain their independent licenses and notices. NSIS uses the zlib compressor and retains its zlib/libpng notice.

## Engineering scope

The preview must retain the limitations in `docs/product/PFA_PRODUCT_READINESS_2026-11-25.md`. It is not a full IEC 60909 implementation or a complete ETAP/PowerFactory replacement. It does not provide AC/DC load flow, OPF, N-1 analysis, or complete end-to-end workflows for every equipment category. IEC 60617 conformance is not claimed beyond individually documented and verified items.
