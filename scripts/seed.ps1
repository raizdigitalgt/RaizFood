$ErrorActionPreference = "Stop"
$backend = Join-Path (Split-Path -Parent $PSScriptRoot) "backend"
Push-Location $backend
try {
    & ./.venv/Scripts/python.exe -m app.cli seed-demo
    if ($LASTEXITCODE -ne 0) { throw "El comando terminó con código $LASTEXITCODE." }
} finally { Pop-Location }
