param([Parameter(Mandatory)][string]$Email, [Parameter(Mandatory)][string]$Name)
$ErrorActionPreference = "Stop"
$backend = Join-Path (Split-Path -Parent $PSScriptRoot) "backend"
Push-Location $backend
try {
    & ./.venv/Scripts/python.exe -m app.cli create-admin --email $Email --name $Name
    if ($LASTEXITCODE -ne 0) { throw "El comando terminó con código $LASTEXITCODE." }
} finally { Pop-Location }
