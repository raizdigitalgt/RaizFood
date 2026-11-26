param([ValidateSet("backend", "frontend")][string]$Service)
$ErrorActionPreference = "Stop"
$project = Split-Path -Parent $PSScriptRoot
$servicePath = Join-Path $project $Service
Push-Location $servicePath
try {
    if ($Service -eq "backend") {
        & ./.venv/Scripts/python.exe -m uvicorn app.main:create_app --factory --reload --port 8000
    } elseif ($Service -eq "frontend") {
        npm.cmd run dev
    } else {
        throw "Indica backend o frontend. Ejecuta un servicio en cada terminal."
    }
    if ($LASTEXITCODE -ne 0) { throw "El servicio terminó con código $LASTEXITCODE." }
} finally { Pop-Location }
