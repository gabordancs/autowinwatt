param(
    [double]$Hours = 6,
    [switch]$UntilComplete,
    [switch]$PlanOnly
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$automationRoot = Join-Path $repoRoot "winwatt_automation"
$python = Join-Path $repoRoot ".venv-winwatt32\Scripts\python.exe"
$plansRoot = Join-Path $automationRoot "data\runtime_maps\autonomous_mapping\plans"
$stamp = Get-Date -Format "yyyyMMddTHHmmss"
$planDir = Join-Path $plansRoot "plan_$stamp"
$env:PYTHONPATH = Join-Path $automationRoot "src"
$env:PYTHONIOENCODING = "utf-8"

Push-Location $automationRoot
try {
    & $python -m winwatt_automation.scripts.plan_autonomous_mapping --output $planDir
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
finally {
    Pop-Location
}

$planPath = Join-Path $planDir "autonomous_mapping_plan.json"
$plan = Get-Content -LiteralPath $planPath -Raw | ConvertFrom-Json
Write-Host "Autonóm mapping terv: $planPath"
Write-Host "Ajánlott művelet: $($plan.recommendation.action)"

if ($PlanOnly -or $plan.recommendation.action -in @("observe_active", "complete")) {
    if ($plan.recommendation.action -eq "observe_active") {
        Write-Host "Már fut WinWatt mapping; második UI-workert nem indítok."
    }
    exit 0
}

$arguments = @{
    Scope = "certification"
    OnlyJob = @($plan.recommendation.jobs)
}
if ($UntilComplete) { $arguments.UntilComplete = $true } else { $arguments.Hours = $Hours }
if ($plan.recommendation.campaign) { $arguments.CampaignDir = [string]$plan.recommendation.campaign }
if ($plan.recommendation.retry_failures) { $arguments.RetryFailures = $true }
if ($plan.recommendation.force_selected_jobs) { $arguments.ForceSelectedJobs = $true }

& (Join-Path $repoRoot "Start-WinWattMapping.ps1") @arguments
exit $LASTEXITCODE
