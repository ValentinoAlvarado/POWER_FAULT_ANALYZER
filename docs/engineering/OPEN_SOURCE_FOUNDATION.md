# POWER_FAULT_ANALYZER — Open-source engineering foundation

This package records the researched reuse strategy for the IEC-oriented symbol system, diagram editor, engineering engines and CIM interoperability.

## Contents

- `RESEARCH/OPEN_SOURCE_REUSE_AND_NORMATIVE_SYMBOL_POLICY.md` — selected architecture and licensing decisions.
- `RESEARCH/qelectrotech-symbol-candidates.csv` — curated starter set of QElectroTech EN 60617 collection assets, pinned to a Git commit and Git blob SHA-1.
- `RESEARCH/software-reuse-matrix.csv` — reuse/adopt/defer/reject matrix.
- `RESEARCH/normative-crosswalk-backlog.csv` — items that still require verification against current normative references.
- `scripts/Acquire-QElectroTechSymbolSeed.ps1` — Windows PowerShell 5.1 downloader with Git blob SHA verification and SHA-256 inventory.
- `docs/architecture/ADR-029-symbol-library-provenance.md` — symbol provenance and licensing ADR.
- `docs/architecture/ADR-030-electrical-model-vs-diagram-document.md` — separation of electrical model and diagram document.
- `docs/architecture/ADR-031-reusable-analysis-and-interchange-adapters.md` — engine and CIM adapter decisions.

## Important status

The QElectroTech collection is a legally reusable **candidate source**, not an automatic certificate of IEC 60617:2026 conformity. Every symbol remains `candidate` until its normative reference and intended diagram context are cross-checked. The official IEC 60617 database is not bundled.

No symbol assets are copied into this research package. The acquisition script downloads selected original files from the pinned public repository and verifies each Git blob hash before saving them under `assets/third_party/qelectrotech-elements/`.

## Apply the seed on Windows

From the PFA repository root after copying this package's `scripts` and `RESEARCH` directories:

```powershell
.\scripts\Acquire-QElectroTechSymbolSeed.ps1
```

The script requires internet access to `raw.githubusercontent.com`. It does not modify Python source code, the solver, the domain model or dependencies.

## Windows symbol seed acquisition

Copy `RESEARCH` and `scripts` from this package into the PFA repository root, then run from the repository root:

```powershell
.\scripts\Acquire-QElectroTechSymbolSeed.ps1
```

The script downloads only the curated original files, checks each upstream Git blob SHA-1 against the pinned manifest, writes SHA-256 values, and preserves `ELEMENTS.LICENSE`. It does not download or mirror the complete symbol collection or any IEC 60617 database.
