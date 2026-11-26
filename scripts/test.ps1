param([switch]$Browser)
$ErrorActionPreference = "Stop"
$project = Split-Path -Parent $PSScriptRoot
Push-Location (Join-Path $project "backend")
try {
    & ./.venv/Scripts/python.exe -m ruff check
    if ($LASTEXITCODE -ne 0) { throw "Falló Ruff." }
    & ./.venv/Scripts/python.exe -m pytest --cov=app --cov-fail-under=80
    if ($LASTEXITCODE -ne 0) { throw "Falló Pytest." }
} finally { Pop-Location }
Push-Location (Join-Path $project "frontend")
try {
    foreach ($check in @("lint", "typecheck", "build")) {
        npm.cmd run $check
        if ($LASTEXITCODE -ne 0) { throw "Falló $check." }
    }
    if ($Browser) {
        npm.cmd run test:e2e
        if ($LASTEXITCODE -ne 0) { throw "Falló Playwright." }
    }
} finally { Pop-Location }
