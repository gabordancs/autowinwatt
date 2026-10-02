param(
    [Parameter(Mandatory = $true)]
    [string]$CampaignDir,
    [Parameter(Mandatory = $true)]
    [int]$SupervisorPid,
    [Parameter(Mandatory = $true)]
    [datetime]$Deadline
)

$ErrorActionPreference = "Stop"
$statePath = Join-Path $CampaignDir "campaign_state.json"
$guardPath = Join-Path $CampaignDir "deadline_guard.json"

function Write-Guard([string]$status) {
    $state = if (Test-Path -LiteralPath $statePath) {
        Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
    } else { $null }
    [ordered]@{
        status = $status
        deadline_local = $Deadline.ToString("o")
        checked_at = (Get-Date).ToString("o")
        supervisor_pid = $SupervisorPid
        campaign_status = if ($state) { $state.status } else { $null }
        current_job = if ($state) { $state.current_job } else { $null }
        current_pid = if ($state) { $state.current_pid } else { $null }
    } | ConvertTo-Json | Set-Content -LiteralPath $guardPath -Encoding UTF8
}

Write-Guard "armed"
while ((Get-Date) -lt $Deadline) {
    if (Test-Path -LiteralPath $statePath) {
        $state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
        if ($state.status -in @("completed", "completed_with_errors", "source_changed", "blocked_desktop")) {
            Write-Guard "campaign_finished_before_deadline"
            exit 0
        }
    }
    Start-Sleep -Seconds 30
}

if (Get-Process -Id $SupervisorPid -ErrorAction SilentlyContinue) {
    & taskkill.exe /PID $SupervisorPid /T /F | Out-Null
}
Write-Guard "stopped_at_deadline"
