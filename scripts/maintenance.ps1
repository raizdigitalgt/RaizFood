$ErrorActionPreference = "Stop"
$backend = Join-Path (Split-Path -Parent $PSScriptRoot) "backend"
Push-Location $backend
try {
    & ./.venv/Scripts/python.exe -m app.maintenance tick
    if ($LASTEXITCODE -ne 0) { throw "El mantenimiento termino con codigo $LASTEXITCODE." }
} finally { Pop-Location }
