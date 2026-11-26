[CmdletBinding()]
param(
    [switch]$SkipRuff,
    [switch]$SkipQtSmoke
)

$ErrorActionPreference = 'Stop'
$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Python = Join-Path $RepositoryRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $Python)) {
    $Python = (Get-Command python -ErrorAction Stop).Source
}

Push-Location $RepositoryRoot
try {
    Write-Host '== QET source seed =='
    $AssetRoot = Join-Path $RepositoryRoot 'assets\third_party\qelectrotech-elements'
    if (-not (Test-Path (Join-Path $AssetRoot 'ELEMENTS.LICENSE'))) {
        throw "QET seed not found. Run .\scripts\Acquire-QElectroTechSymbolSeed.ps1 first."
    }

    if (-not $SkipRuff) {
        # This verifier owns the QET importer/renderer quality gate, not the
        # repository-wide lint baseline. Keep unrelated legacy lint debt from
        # blocking this focused acceptance path.
        $QetPythonFiles = @(
            'src/power_fault_analyzer/infrastructure/symbols/__init__.py',
            'src/power_fault_analyzer/infrastructure/symbols/qet_elmt.py',
            'src/power_fault_analyzer/infrastructure/symbols/qet_catalog.py',
            'src/power_fault_analyzer/interfaces/desktop/workbench/qet_symbol_item.py',
            'src/power_fault_analyzer/interfaces/desktop/workbench/qet_symbol_browser.py',
            'tests/unit/infrastructure/symbols/test_qet_catalog.py',
            'tests/unit/infrastructure/symbols/test_qet_elmt.py',
            'tests/unit/interfaces/desktop/workbench/test_qet_symbol_item.py'
        )

        foreach ($relativePath in $QetPythonFiles) {
            $absolutePath = Join-Path $RepositoryRoot $relativePath
            if (-not (Test-Path -LiteralPath $absolutePath -PathType Leaf)) {
                throw "QET lint target not found: $relativePath"
            }
        }

        Write-Host '== Ruff lint: QET importer and renderer =='
        & $Python -m ruff check @QetPythonFiles
        if ($LASTEXITCODE -ne 0) { throw "QET Ruff lint failed with exit code $LASTEXITCODE." }

        Write-Host '== Ruff format: QET importer and renderer =='
        & $Python -m ruff format --check @QetPythonFiles
        if ($LASTEXITCODE -ne 0) { throw "QET Ruff format check failed with exit code $LASTEXITCODE." }
    }

    Write-Host '== Compileall =='
    & $Python -m compileall -q src tests scripts
    if ($LASTEXITCODE -ne 0) { throw "Compileall failed with exit code $LASTEXITCODE." }

    Write-Host '== Complete Pytest suite =='
    & $Python -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw "Pytest failed with exit code $LASTEXITCODE." }

    if (-not $SkipQtSmoke) {
        Write-Host '== PySide6 source-symbol render smoke =='
        $PreviousQtPlatform = $env:QT_QPA_PLATFORM
        $env:QT_QPA_PLATFORM = 'offscreen'
        try {
            @'
from pathlib import Path
from PySide6.QtWidgets import QApplication, QGraphicsScene
from power_fault_analyzer.infrastructure.symbols.qet_catalog import load_qet_symbol_catalog
from power_fault_analyzer.interfaces.desktop.workbench.qet_symbol_item import QETSymbolItem

root = Path.cwd()
catalog = load_qet_symbol_catalog(
    root / "RESEARCH" / "qelectrotech-symbol-candidates.csv",
    root / "assets" / "third_party" / "qelectrotech-elements",
)
symbol = catalog.by_asset_id("IEC-GEN-SYNC-3PH-NEUTRAL")
symbol.require_connectable()
app = QApplication.instance() or QApplication([])
scene = QGraphicsScene()
item = QETSymbolItem(symbol, require_connectable=True)
scene.addItem(item)
assert len(symbol.terminals) == 4, f"Expected 4 source terminals, found {len(symbol.terminals)}"
assert item.boundingRect().width() > 0 and item.boundingRect().height() > 0
assert symbol.source_git_blob_sha1
print(f"QET renderer PASS: {symbol.name_for('en')} | terminals={len(symbol.terminals)} | blob={symbol.source_git_blob_sha1}")
'@ | & $Python -
            if ($LASTEXITCODE -ne 0) { throw "PySide6 symbol render smoke failed with exit code $LASTEXITCODE." }
        }
        finally {
            $env:QT_QPA_PLATFORM = $PreviousQtPlatform
        }
    }

    Write-Host 'QET symbol importer verification completed successfully.' -ForegroundColor Green
}
finally {
    Pop-Location
}
