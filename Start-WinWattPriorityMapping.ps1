param(
    [string]$RunId = "",
    [switch]$RoomOnly
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $MyInvocation.MyCommand.Path
$automation = Join-Path $repo "winwatt_automation"
$python = Join-Path $repo ".venv-winwatt32\Scripts\python.exe"
$profile = Join-Path $repo "docs\winwatt_local_profile_20260929.json"
$campaign = Join-Path $automation "data\runtime_maps\certification_mapping\mainroadmap_20260929T230344"
$state = Get-Content -Raw (Join-Path $campaign "campaign_state.json") | ConvertFrom-Json
if (-not $RunId) { $RunId = "priority_" + (Get-Date -Format "yyyyMMddTHHmmss") }
$output = Join-Path $automation "data\runtime_maps\priority_mapping\$RunId"
$buildingProject = Join-Path $campaign "jobs\recursive_building_mapping\full_authorized_sandbox\prepared.wwp"
$buildingGraph = Join-Path $campaign "jobs\recursive_building_mapping\graph"
# HTML Help runs outside the WinWatt process and can survive an earlier crawl.
# Its foreground window prevents the connector from accepting the otherwise
# healthy WinWatt main frame, so clear only WinWatt's own orphaned CHM viewers.
Get-CimInstance Win32_Process | Where-Object {
    $_.Name -eq "hh.exe" -and $_.CommandLine -match "Bausoft.*WinWatt.*WinWatt32\.chm"
} | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
$active = @(Get-CimInstance Win32_Process | Where-Object {
    $_.Name -in @("WinWatt32.exe", "python.exe") -and
    $_.CommandLine -match "winwatt|mapping"
})
if ($active.Count) { throw "Már fut WinWatt vagy mappingfolyamat." }
$env:PYTHONPATH = Join-Path $automation "src"
$env:PYTHONIOENCODING = "utf-8"
Push-Location $automation
try {
    $arguments = @(
        "-m", "winwatt_automation.scripts.priority_mapping_executor",
        "--profile", $profile, "--source", $state.source_project,
        "--building-project", $buildingProject, "--building-graph", $buildingGraph,
        "--output", $output,
        "--room-reference-graph", (Join-Path $automation "data\runtime_maps\room_deep_runs\local_summer_20260828T081333\graph.json"),
        "--room-reference-graph", (Join-Path $automation "data\runtime_maps\room_deep_runs\local_boundaries_20260827T220124\graph.json")
    )
    if ($RoomOnly) { $arguments += "--room-only" }
    & $python @arguments
    exit $LASTEXITCODE
}
finally { Pop-Location }
