# Public branch maintenance and release procedure

## Source branch and integration

- `main` is the default public branch and the stable integration baseline.
- `product-reboot` contains the consolidated product implementation under review.
- Develop and validate changes on a feature branch or `product-reboot`; do not force-push either public branch.
- Promote `product-reboot` to `main` through a GitHub Pull Request after reviewing the complete diff, CI results, legal notices and release configuration.
- Do not change the default branch merely to make an unfinished implementation appear to be the stable release.

## Windows build validation

Run **Actions → Windows desktop release → Run workflow** against `product-reboot` to build the portable Windows ZIP and inspect the uploaded artifacts. This workflow does not publish a GitHub Release when run manually.

The workflow uses Python 3.13 x64, the pinned QElectroTech symbol collection and Cairo runtime; it runs source, Qt and frozen-application acceptance checks and produces the ZIP, SBOM, license inventory, notices, build metadata and checksums.

## Tagged release gate

A pushed `v*` tag builds the same artifacts and runs `scripts/verify_release_license_review.py`. A tag must not be pushed until every dependency with unresolved license metadata has been investigated against the exact package version and recorded in `RELEASE_LICENSE_REVIEW.csv`. Never infer or fabricate a license approval. A failed review must block publication.

The current public release asset is `PFA-Windows-x64.zip`. The NSIS source is retained for future use but is not part of the active release workflow. The website download control activates only after a published release contains the expected ZIP asset.

## Promotion checklist

1. Review `main...product-reboot` and confirm no unrelated deletions or generated artifacts.
2. Run the Windows workflow manually on `product-reboot` and inspect the actual ZIP on a clean Windows environment.
3. Review application and third-party licensing; complete the exact-version release review register.
4. Open and review a Pull Request from `product-reboot` to `main`.
5. Merge only after required checks and review pass.
6. Run the release workflow on `main`, then create and push a version tag only when the release gate is ready.