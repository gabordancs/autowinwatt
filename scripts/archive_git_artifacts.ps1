param(
    [Parameter(Mandatory = $true)]
    [string]$Destination
)

$ErrorActionPreference = 'Stop'

$repo = (git rev-parse --show-toplevel).Trim()
if (-not $repo) {
    throw 'Not inside a Git repository.'
}
$repo = [System.IO.Path]::GetFullPath($repo)
$destinationFull = [System.IO.Path]::GetFullPath($Destination)
if ($destinationFull.StartsWith($repo + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'The artifact archive must be outside the Git repository.'
}
if (Test-Path -LiteralPath $destinationFull) {
    throw "Archive destination already exists: $destinationFull"
}

$tracked = @(& git -c core.quotepath=false ls-files)
if ($LASTEXITCODE -ne 0) {
    throw 'git ls-files failed.'
}

$prefixes = @(
    '.codex-remote-attachments/',
    'data/delceg56/',
    'data/webwatt_jobs/',
    'output/',
    'outputs/',
    'tmp/',
    'winwatt_automation/data/certificate_builds/',
    'winwatt_automation/data/knowledge/certification_corpus/',
    'winwatt_automation/data/knowledge/global_mapping/',
    'winwatt_automation/data/oeny_reconstruction/',
    'winwatt_automation/data/run_logs/',
    'winwatt_automation/data/runtime_maps/',
    'winwatt_automation/data/snapshots/',
    'winwatt_automation/x/'
)
$exact = @(
    'winwatt_automation/data/knowledge/knowledge_store.json',
    'winwatt_automation/data/knowledge/navigation_knowledge.json',
    'winwatt_automation/tests/test.xml'
)

function Test-ArtifactPath([string]$Path) {
    $normalized = $Path.Replace('\', '/')
    foreach ($prefix in $prefixes) {
        if ($normalized.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)) {
            return $true
        }
    }
    if ($exact -contains $normalized) {
        return $true
    }
    $name = [System.IO.Path]::GetFileName($normalized)
    $extension = [System.IO.Path]::GetExtension($normalized).ToLowerInvariant()
    if ($name.EndsWith('.checkpoint.json', [System.StringComparison]::OrdinalIgnoreCase)) {
        return $true
    }
    if ($extension -in @('.log', '.pdf', '.png', '.jpg', '.jpeg', '.wwp', '.bak')) {
        return $true
    }
    if ($name -match '\.wwp\.' -or $name -match '\.tmp\d*$') {
        return $true
    }
    return $false
}

$selected = @($tracked | Where-Object { Test-ArtifactPath $_ } | Sort-Object -Unique)
if ($selected.Count -eq 0) {
    throw 'No tracked artifacts matched the archival policy.'
}

$filesRoot = Join-Path $destinationFull 'files'
[System.IO.Directory]::CreateDirectory($filesRoot) | Out-Null
$manifestFiles = [System.Collections.Generic.List[object]]::new()
$totalBytes = [int64]0

foreach ($relative in $selected) {
    $source = Join-Path $repo ($relative.Replace('/', [System.IO.Path]::DirectorySeparatorChar))
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
        continue
    }
    $target = Join-Path $filesRoot ($relative.Replace('/', [System.IO.Path]::DirectorySeparatorChar))
    [System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($target)) | Out-Null
    [System.IO.File]::Copy($source, $target, $false)
    $item = Get-Item -LiteralPath $source
    $hash = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant()
    $totalBytes += $item.Length
    $manifestFiles.Add([ordered]@{
        path = $relative
        bytes = [int64]$item.Length
        sha256 = $hash
    })
}

$manifest = [ordered]@{
    schema_version = 1
    created_at = (Get-Date).ToUniversalTime().ToString('o')
    repository = $repo
    branch = (git branch --show-current).Trim()
    commit = (git rev-parse HEAD).Trim()
    file_count = $manifestFiles.Count
    total_bytes = $totalBytes
    policy = 'generated runtime evidence, logs, screenshots, PDFs, WWP projects, customer-related outputs and large generated knowledge stores'
    files = $manifestFiles
}
$manifestPath = Join-Path $destinationFull 'manifest.json'
[System.IO.File]::WriteAllText(
    $manifestPath,
    (($manifest | ConvertTo-Json -Depth 5) + [Environment]::NewLine),
    [System.Text.UTF8Encoding]::new($false)
)
$manifestHash = (Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256).Hash.ToLowerInvariant()
[System.IO.File]::WriteAllText(
    (Join-Path $destinationFull 'manifest.sha256'),
    ($manifestHash + '  manifest.json' + [Environment]::NewLine),
    [System.Text.UTF8Encoding]::new($false)
)

[ordered]@{
    status = 'passed'
    destination = $destinationFull
    file_count = $manifestFiles.Count
    total_bytes = $totalBytes
    manifest = $manifestPath
    manifest_sha256 = $manifestHash
} | ConvertTo-Json
