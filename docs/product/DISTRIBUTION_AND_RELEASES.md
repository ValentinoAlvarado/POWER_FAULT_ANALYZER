# Desktop distribution and public release page

PFA remains a desktop engineering application. The public website is its distribution and documentation front door; it is not a replacement for the engineering editor.

## Windows package

- The product is distributed as an install-free, standalone Windows x64 desktop folder in a ZIP archive. The website is its download/documentation front door; the engineering editor remains a native desktop application.
- Python 3.13 x64 is the release build toolchain.
- The release workflow installs the `desktop`, `reports` and `release` extras.
- The pinned QElectroTech symbol seed is acquired and hash-verified before packaging.
- PyInstaller builds an `onedir` application because the Qt plugin/runtime tree is more diagnosable than a one-file executable.
- The release asset is `PFA-Windows-x64.zip`; it includes the executable, runtime dependencies, source symbol collection, attribution/license notices, and SHA-256 checksum. It is a portable `onedir` ZIP, not an MSI installer; extract the archive and launch `POWER_FAULT_ANALYZER.exe`.
- A release is published only from a `v*` tag after lint, formatting, compile, tests and QET/Qt smoke checks pass.
- **Publication is currently license-blocked:** the repository root `LICENSE` file is empty. Do not publish a public binary or describe the application as OSI-licensed open source until the project selects and commits a license and the Qt/PySide6 redistribution obligations are reviewed. QElectroTech element assets retain their separate CC BY 3.0 attribution and terms.

## Website deployment

1. Publish the repository to GitHub.
2. Edit `website/index.html` and replace `YOUR_GITHUB_OWNER/POWER_FAULT_ANALYZER` with the exact public owner/repository slug.
3. Enable GitHub Pages with **GitHub Actions** as the build/deployment source.
4. Push to `main` to deploy the download page.
5. Create a version tag such as `v0.2.0` to run the verified Windows build and publish the release ZIP.

The download page queries the latest GitHub Release and enables the download only if the expected ZIP asset exists. Until a repository slug and public release are configured, it deliberately shows a non-download state instead of a broken or invented link.
