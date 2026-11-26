# POWER_FAULT_ANALYZER — create the planned workspace directories.
# Run this script from any PowerShell working directory:
#   .\scripts\bootstrap_structure.ps1

$Root = Split-Path -Parent $PSScriptRoot
if ((Split-Path $Root -Leaf) -ne "POWER_FAULT_ANALYZER") {
    throw "The script must be located in the scripts directory of POWER_FAULT_ANALYZER."
}

$Directories = @(
    "data\examples",
    "data\benchmarks",
    "data\reference_cases",
    "docs\architecture\adr",
    "docs\engineering",
    "docs\standards",
    "src\power_fault_analyzer\domain\entities",
    "src\power_fault_analyzer\domain\value_objects",
    "src\power_fault_analyzer\domain\aggregates",
    "src\power_fault_analyzer\domain\interfaces",
    "src\power_fault_analyzer\domain\events",
    "src\power_fault_analyzer\domain\exceptions",
    "src\power_fault_analyzer\domain\services",
    "src\power_fault_analyzer\domain\enums",
    "src\power_fault_analyzer\application\commands",
    "src\power_fault_analyzer\application\queries",
    "src\power_fault_analyzer\application\use_cases",
    "src\power_fault_analyzer\application\services",
    "src\power_fault_analyzer\application\ports",
    "src\power_fault_analyzer\electrical\bases",
    "src\power_fault_analyzer\electrical\units",
    "src\power_fault_analyzer\electrical\impedance",
    "src\power_fault_analyzer\electrical\symmetrical_components",
    "src\power_fault_analyzer\electrical\grounding",
    "src\power_fault_analyzer\electrical\transformer_models",
    "src\power_fault_analyzer\equipment\sources",
    "src\power_fault_analyzer\equipment\transformers",
    "src\power_fault_analyzer\equipment\transmission",
    "src\power_fault_analyzer\equipment\motors",
    "src\power_fault_analyzer\equipment\loads",
    "src\power_fault_analyzer\equipment\converters",
    "src\power_fault_analyzer\equipment\switching",
    "src\power_fault_analyzer\network\topology",
    "src\power_fault_analyzer\network\connectivity",
    "src\power_fault_analyzer\network\ybus",
    "src\power_fault_analyzer\network\sequence_networks",
    "src\power_fault_analyzer\faults\models",
    "src\power_fault_analyzer\faults\strategies",
    "src\power_fault_analyzer\faults\analysis",
    "src\power_fault_analyzer\engines\academic",
    "src\power_fault_analyzer\engines\iec60909",
    "src\power_fault_analyzer\infrastructure\numerical",
    "src\power_fault_analyzer\infrastructure\graph",
    "src\power_fault_analyzer\infrastructure\persistence",
    "src\power_fault_analyzer\infrastructure\serialization",
    "src\power_fault_analyzer\infrastructure\adapters",
    "src\power_fault_analyzer\results",
    "src\power_fault_analyzer\validation",
    "src\power_fault_analyzer\reporting",
    "src\power_fault_analyzer\interfaces\api",
    "src\power_fault_analyzer\interfaces\desktop",
    "src\power_fault_analyzer\bootstrap",
    "frontend\web\src",
    "frontend\web\public",
    "frontend\web\tests",
    "tests\unit\domain\entities",
    "tests\unit\domain\aggregates",
    "tests\unit\domain\services",
    "tests\contract",
    "tests\integration",
    "tests\property_based",
    "tests\regression",
    "tests\benchmarks"
)

foreach ($Directory in $Directories) {
    New-Item -ItemType Directory -Force -Path (Join-Path $Root $Directory) | Out-Null
}

$PackageDirectories = @(
    "src\power_fault_analyzer\application",
    "src\power_fault_analyzer\application\commands",
    "src\power_fault_analyzer\application\queries",
    "src\power_fault_analyzer\application\use_cases",
    "src\power_fault_analyzer\application\services",
    "src\power_fault_analyzer\application\ports",
    "src\power_fault_analyzer\electrical",
    "src\power_fault_analyzer\electrical\bases",
    "src\power_fault_analyzer\electrical\units",
    "src\power_fault_analyzer\electrical\impedance",
    "src\power_fault_analyzer\electrical\symmetrical_components",
    "src\power_fault_analyzer\electrical\grounding",
    "src\power_fault_analyzer\electrical\transformer_models",
    "src\power_fault_analyzer\equipment",
    "src\power_fault_analyzer\equipment\sources",
    "src\power_fault_analyzer\equipment\transformers",
    "src\power_fault_analyzer\equipment\transmission",
    "src\power_fault_analyzer\equipment\motors",
    "src\power_fault_analyzer\equipment\loads",
    "src\power_fault_analyzer\equipment\converters",
    "src\power_fault_analyzer\equipment\switching",
    "src\power_fault_analyzer\network",
    "src\power_fault_analyzer\network\topology",
    "src\power_fault_analyzer\network\connectivity",
    "src\power_fault_analyzer\network\ybus",
    "src\power_fault_analyzer\network\sequence_networks",
    "src\power_fault_analyzer\faults",
    "src\power_fault_analyzer\faults\models",
    "src\power_fault_analyzer\faults\strategies",
    "src\power_fault_analyzer\faults\analysis",
    "src\power_fault_analyzer\engines",
    "src\power_fault_analyzer\engines\academic",
    "src\power_fault_analyzer\engines\iec60909",
    "src\power_fault_analyzer\infrastructure",
    "src\power_fault_analyzer\infrastructure\numerical",
    "src\power_fault_analyzer\infrastructure\graph",
    "src\power_fault_analyzer\infrastructure\persistence",
    "src\power_fault_analyzer\infrastructure\serialization",
    "src\power_fault_analyzer\infrastructure\adapters",
    "src\power_fault_analyzer\results",
    "src\power_fault_analyzer\validation",
    "src\power_fault_analyzer\reporting",
    "src\power_fault_analyzer\interfaces",
    "src\power_fault_analyzer\interfaces\api",
    "src\power_fault_analyzer\interfaces\desktop",
    "src\power_fault_analyzer\bootstrap"
)

foreach ($Directory in $PackageDirectories) {
    $InitFile = Join-Path (Join-Path $Root $Directory) "__init__.py"
    if (-not (Test-Path $InitFile)) {
        New-Item -ItemType File -Path $InitFile | Out-Null
    }
}

Write-Host "POWER_FAULT_ANALYZER workspace structure is ready." -ForegroundColor Green
Write-Host "Root: $Root" -ForegroundColor Cyan
Write-Host "Directories processed: $($Directories.Count)" -ForegroundColor Gray
