$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pidFile = Join-Path $projectRoot 'data\local-processes.json'
if (-not (Test-Path -LiteralPath $pidFile)) { Write-Output 'No recorded local session.'; exit 0 }
$processIds = Get-Content -LiteralPath $pidFile -Raw | ConvertFrom-Json
foreach ($processId in $processIds) {
    # Only stop a still-matching process from our recorded session, with its children.
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $processId" -ErrorAction SilentlyContinue
    if ($process -and $process.CommandLine -and ($process.CommandLine.Contains('app.main:app') -or $process.CommandLine.Contains('app.worker') -or $process.CommandLine.Contains('node_modules/next/dist/bin/next'))) {
        taskkill.exe /PID $processId /T /F | Out-Null
    }
}
Remove-Item -LiteralPath $pidFile
Write-Output 'Stopped the recorded RAGForge session.'
