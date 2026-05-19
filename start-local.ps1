# Doane SF Mission Control -- local dev launcher
param([switch]$ForceDeps)

$ErrorActionPreference = 'Stop'
$Root = $PSScriptRoot
$Log = "$Root\.hub-logs\app.log"
$LogErr = "$Root\.hub-logs\app.err"

# Create log dir, wipe old logs
New-Item -ItemType Directory -Path "$Root\.hub-logs" -Force | Out-Null
if (Test-Path $Log)    { Remove-Item $Log }
if (Test-Path $LogErr) { Remove-Item $LogErr }

# Activate venv — create it automatically if missing
$Venv = "$Root\.venv\Scripts\Activate.ps1"
if (-not (Test-Path $Venv)) {
    Write-Host "Creating virtual environment..." -ForegroundColor Cyan
    python -m venv "$Root\.venv"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: failed to create .venv. Is Python in PATH?" -ForegroundColor Red
        exit 1
    }
}
. $Venv

# Install deps if requested or venv looks empty
if ($ForceDeps -or (-not (Test-Path "$Root\.venv\Lib\site-packages\flask"))) {
    Write-Host "Installing dependencies..." -ForegroundColor Cyan
    pip install -r "$Root\requirements.txt" --quiet
}

# Set env vars for Flask (Debug mode for local dev)
$env:FLASK_DEBUG = if ($env:FLASK_ENV -eq 'production') { '0' } else { '1' }
$env:FLAGS_use_mkldnn = '0'

# Get LAN IP (skip 169.254.x.x, vEthernet, WSL)
$IP = (Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object { $_.IPAddress -notlike '169.254.*' -and
                   $_.InterfaceAlias -notlike '*vEthernet*' -and
                   $_.InterfaceAlias -notlike '*WSL*' -and
                   $_.IPAddress -ne '127.0.0.1' } |
    Select-Object -First 1).IPAddress

$Port = if ($env:PORT) { $env:PORT } else { '5000' }
Write-Host "Starting SF Mission Control on http://${IP}:${Port}" -ForegroundColor Green

python -u "$Root\app.py" >> $Log 2>> $LogErr
