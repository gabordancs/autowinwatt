param(
    [double]$Hours = 6,
    [string]$Project = "",
    [switch]$ResumeLatest,
    [switch]$UntilComplete,
    [switch]$SkipBackground,
    [switch]$RetryFailures,
    [ValidateSet("buildings", "structures", "certification")]
    [string]$Scope = "buildings"
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$automationRoot = Join-Path $repoRoot "winwatt_automation"
$python = Join-Path $repoRoot ".venv-winwatt32\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "A 32 bites Python-környezet nem található: $python"
}

$env:PYTHONPATH = Join-Path $automationRoot "src"
$env:PYTHONIOENCODING = "utf-8"
$arguments = @("-m", "winwatt_automation.scripts.certification_mapping_executor")
if ($UntilComplete) {
    if ($PSBoundParameters.ContainsKey("Hours")) {
        throw "Az -UntilComplete és a -Hours együtt nem használható."
    }
    $arguments += @("--until-complete", "--max-desktop-retries", "0")
}
else {
    $arguments += @("--hours", $Hours.ToString([Globalization.CultureInfo]::InvariantCulture))
}
if ($Project) { $arguments += @("--project", $Project) }
if ($ResumeLatest) { $arguments += "--resume-latest" }
if ($SkipBackground) { $arguments += "--skip-background" }
if ($RetryFailures) { $arguments += "--retry-background-failures" }
$arguments += @("--background-scope", $Scope)
if ($Scope -eq "certification") { $arguments += "--background-only" }

Write-Host "WinWatt mapping indul. A Windows munkamenet maradjon feloldva."
Write-Host "Leállítás: Ctrl+C. Folytatás: .\Start-WinWattMapping.ps1 -ResumeLatest"
Write-Host "Korábbi hibák külön újrapróbálása: -ResumeLatest -RetryFailures"
if ($UntilComplete) {
    Write-Host "Futási mód: időkorlát nélkül, a várólista befejezéséig."
}
Push-Location $automationRoot
try {
    & $python @arguments
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
