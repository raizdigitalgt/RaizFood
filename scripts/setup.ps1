param([string]$Python = "python")
$ErrorActionPreference = "Stop"
$project = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $project "backend"
$frontend = Join-Path $project "frontend"
$venvPython = Join-Path $backend ".venv/Scripts/python.exe"
Push-Location $project
try {
    & $Python -c 'import sys; raise SystemExit(sys.version_info[:2] != (3, 14))'
    if ($LASTEXITCODE -ne 0) { throw "Usa Python 3.14 o indica su ruta con -Python." }
    if (-not (Test-Path -LiteralPath $venvPython)) {
        & $Python -m venv (Join-Path $backend ".venv")
        if ($LASTEXITCODE -ne 0) { throw "No se pudo crear el entorno virtual." }
    }
    & $venvPython -m pip install -r (Join-Path $backend "requirements-dev.txt")
    if ($LASTEXITCODE -ne 0) { throw "Falló la instalación de Python." }
    if (-not (Test-Path -LiteralPath ".env")) {
        $secret = & $venvPython -c 'import secrets; print(secrets.token_hex(32))'
        if ($LASTEXITCODE -ne 0) { throw "No se pudo generar el secreto local." }
        $configuration = (Get-Content -Raw -Encoding utf8 -LiteralPath ".env.example").Replace("JWT_SECRET_KEY=", "JWT_SECRET_KEY=$secret")
        [IO.File]::WriteAllText((Join-Path $project ".env"), $configuration, [Text.UTF8Encoding]::new($false))
    }
    & $venvPython -m alembic -c (Join-Path $backend "alembic.ini") upgrade head
    if ($LASTEXITCODE -ne 0) { throw "Falló la migración." }
    Push-Location $backend
    try {
        & $venvPython -m app.cli seed-plans
        if ($LASTEXITCODE -ne 0) { throw "Falló la inicialización de planes." }
    } finally { Pop-Location }
    & npm.cmd --prefix $frontend ci
    if ($LASTEXITCODE -ne 0) { throw "Falló npm ci." }
} finally { Pop-Location }
