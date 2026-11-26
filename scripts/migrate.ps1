$ErrorActionPreference = "Stop"
$backend = Join-Path (Split-Path -Parent $PSScriptRoot) "backend"
Push-Location $backend
try {
    & ./.venv/Scripts/python.exe -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw "El comando terminó con código $LASTEXITCODE." }
} finally { Pop-Location }
