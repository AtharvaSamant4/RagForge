$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) { throw 'Create .venv and install backend requirements first. See README.md.' }
if (-not (Test-Path -LiteralPath (Join-Path $projectRoot 'frontend\node_modules'))) { throw 'Run npm ci in frontend first. See README.md.' }
New-Item -ItemType Directory -Force (Join-Path $projectRoot 'data') | Out-Null
& $pythonExe -m alembic -c backend/alembic.ini upgrade head
if ($LASTEXITCODE -ne 0) { throw 'Database migration failed' }
$env:PYTHONPATH = Join-Path $projectRoot 'backend'
$nodeExecutable = (Get-Command node.exe).Source
$apiProcess = Start-Process -FilePath $pythonExe -ArgumentList @('-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000','--no-access-log') -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $projectRoot 'data\api.log') -RedirectStandardError (Join-Path $projectRoot 'data\api-error.log')
$workerProcess = Start-Process -FilePath $pythonExe -ArgumentList @('-m','app.worker') -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $projectRoot 'data\worker.log') -RedirectStandardError (Join-Path $projectRoot 'data\worker-error.log')
$webProcess = Start-Process -FilePath $nodeExecutable -ArgumentList @('node_modules/next/dist/bin/next','dev','--hostname','127.0.0.1') -WorkingDirectory (Join-Path $projectRoot 'frontend') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $projectRoot 'data\web.log') -RedirectStandardError (Join-Path $projectRoot 'data\web-error.log')
$processIds = @($apiProcess.Id,$workerProcess.Id,$webProcess.Id)
ConvertTo-Json -InputObject $processIds | Set-Content -LiteralPath (Join-Path $projectRoot 'data\local-processes.json')
Write-Output 'RAGForge is starting: http://localhost:3000 (API: http://localhost:8000/docs)'
Write-Output 'Logs: data/. Stop with .\scripts\stop-local.ps1'
