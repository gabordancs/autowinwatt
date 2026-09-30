param(
    [string]$Source = "",
    [string]$Output = "",
    [string]$ZoneName = "AUTO_HEATED_ZONE_WORKFLOW",
    [string]$SystemName = "AUTO_HEATING_WORKFLOW"
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$automationRoot = Join-Path $repoRoot "winwatt_automation"
$python = Join-Path $repoRoot ".venv-winwatt32\Scripts\python.exe"
$profile = Join-Path $repoRoot "docs\winwatt_local_profile_20260929.json"
if (-not (Test-Path -LiteralPath $python)) {
    throw "A 32 bites Python-környezet nem található: $python"
}
if (-not $Source) {
    $Source = Join-Path $automationRoot "data\runtime_maps\full_authorized_sandbox\certification_seed_20260929b\prepared.wwp"
}
if (-not $Output) {
    $stamp = Get-Date -Format "yyyyMMddTHHmmss"
    $Output = Join-Path $automationRoot "data\runtime_maps\heating_certification_workflow_$stamp"
}

$env:PYTHONPATH = Join-Path $automationRoot "src"
$env:PYTHONIOENCODING = "utf-8"
Push-Location $automationRoot
try {
    & $python -m winwatt_automation.scripts.run_heating_certification_workflow `
        --profile $profile --source $Source --output $Output `
        --zone-name $ZoneName --system-name $SystemName
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
