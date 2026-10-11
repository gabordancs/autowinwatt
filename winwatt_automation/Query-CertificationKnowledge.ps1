param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $QueryArguments
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot ".venv-winwatt32\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    $python = "python"
}

$previousPythonPath = $env:PYTHONPATH
$previousPythonIoEncoding = $env:PYTHONIOENCODING
try {
    $env:PYTHONPATH = Join-Path $PSScriptRoot "src"
    $env:PYTHONIOENCODING = "utf-8"
    & $python -m winwatt_automation.scripts.query_certification_domain_knowledge @QueryArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Certification knowledge query failed with exit code $LASTEXITCODE."
    }
}
finally {
    $env:PYTHONPATH = $previousPythonPath
    $env:PYTHONIOENCODING = $previousPythonIoEncoding
}
