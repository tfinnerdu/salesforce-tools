# Doane SF Mission Control -- local dev launcher
#
# CONTRACT
#   Zero-arg invocation ("powershell -File .\start-local.ps1") starts the
#   app in its default dev configuration -- no flags required, no prompts.
#   Flags below are for humans running the script directly.
#
# There is no -Wipe/-Reseed/-NoSeed here -- this app has no local-file DB to
# wipe or fixture data to seed. Postgres tables persist across runs by design
# (init_db is CREATE TABLE IF NOT EXISTS); SHOW_MOCK=true is how you get
# demoable data without touching a live org or a local DB at all.

param(
    [switch]$Foreground,
    [int]$Port = 0,
    [switch]$SkipDeps,
    [switch]$ForceDeps,
    [switch]$Debug,
    [switch]$Help
)

if ($Help) {
    Write-Host @"
Doane SF Mission Control -- local dev launcher

USAGE
  .\start-local.ps1                # start Flask (background + health wait)
  .\start-local.ps1 -Foreground    # run attached, logs stream in-line
  .\start-local.ps1 -Port 5010     # override port
  .\start-local.ps1 -SkipDeps      # skip the pip install check
  .\start-local.ps1 -ForceDeps     # reinstall deps even if present
  .\start-local.ps1 -Debug         # verbose + FLASK_DEBUG=1
  .\start-local.ps1 -Help          # print this usage and exit
"@
    exit 0
}

$ErrorActionPreference = 'Stop'
$Root = $PSScriptRoot
$Log = "$Root\.hub-logs\app.log"
$LogErr = "$Root\.hub-logs\app.err"

# Create log dir, wipe old logs
New-Item -ItemType Directory -Path "$Root\.hub-logs" -Force | Out-Null
if (Test-Path $Log)    { Remove-Item $Log }
if (Test-Path $LogErr) { Remove-Item $LogErr }

# Activate venv -- create it automatically if missing
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
if (-not $SkipDeps -and ($ForceDeps -or (-not (Test-Path "$Root\.venv\Lib\site-packages\flask")))) {
    Write-Host "Installing dependencies..." -ForegroundColor Cyan
    pip install -r "$Root\requirements.txt" --quiet
}

# Load .env into the process environment so it takes precedence over hub-injected vars
$EnvFile = "$Root\.env"
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') {
            $key = $matches[1]
            $raw = $matches[2]
            # Quoted values keep '#' and whitespace verbatim; unquoted values
            # drop a trailing " #..." inline comment (space required before
            # '#' so a bare fragment/anchor like "...page#section" survives).
            if ($raw -match '^"([^"]*)"') {
                $val = $matches[1]
            } elseif ($raw -match "^'([^']*)'") {
                $val = $matches[1]
            } else {
                $val = ($raw -replace '\s+#.*$', '').Trim()
            }
            [System.Environment]::SetEnvironmentVariable($key, $val, 'Process')
        }
    }
}

# Werkzeug reloader isolation -- required, not optional. A parent Flask
# process (or a hub itself running under the reloader) can leave these set;
# inheriting them makes this child think it owns a socket that doesn't exist
# in this process, and it dies with WinError 10038.
Remove-Item Env:WERKZEUG_RUN_MAIN  -ErrorAction SilentlyContinue
Remove-Item Env:WERKZEUG_SERVER_FD -ErrorAction SilentlyContinue

# Env vars for Flask
$env:PORT = if ($Port -gt 0) { "$Port" } elseif ($env:PORT) { $env:PORT } else { '5000' }
$env:FLASK_DEBUG = if ($Debug) { '1' } elseif ($env:FLASK_ENV -eq 'production') { '0' } else { '1' }

# Get LAN IP (skip 169.254.x.x, vEthernet, WSL)
$IP = (Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object { $_.IPAddress -notlike '169.254.*' -and
                   $_.InterfaceAlias -notlike '*vEthernet*' -and
                   $_.InterfaceAlias -notlike '*WSL*' -and
                   $_.IPAddress -ne '127.0.0.1' } |
    Select-Object -First 1).IPAddress

Write-Host "Starting SF Mission Control on http://${IP}:$($env:PORT)" -ForegroundColor Green

if ($Foreground) {
    # Attached: logs stream in-line, Ctrl+C stops it directly. Nothing to
    # health-probe here -- the terminal itself is the log.
    $ErrorActionPreference = 'Continue'
    python -u "$Root\app.py"
    exit $LASTEXITCODE
}

# Background: redirect output to the log files, wait for /api/v1/health, then
# stay attached to the child (Ctrl+C stops the tree) -- same lifetime
# contract as before, just with a real readiness gate up front.
$app = Start-Process -FilePath python `
    -ArgumentList '-u', "$Root\app.py" `
    -RedirectStandardOutput $Log `
    -RedirectStandardError  $LogErr `
    -PassThru -NoNewWindow

$ready = $false
for ($i = 0; $i -lt 30; $i++) {
    if ($app.HasExited) {
        Write-Host "ERROR: process exited before becoming healthy (exit code $($app.ExitCode))." -ForegroundColor Red
        Get-Content $LogErr -ErrorAction SilentlyContinue | Select-Object -Last 30
        exit 1
    }
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:$($env:PORT)/api/v1/health" `
             -UseBasicParsing -TimeoutSec 2
        if ($r.StatusCode -eq 200) { $ready = $true; break }
    } catch { Start-Sleep -Seconds 1 }
}
if (-not $ready) {
    Write-Host "ERROR: service did not respond on /api/v1/health within 30s." -ForegroundColor Red
    Get-Content $LogErr -ErrorAction SilentlyContinue | Select-Object -Last 30
    Stop-Process -Id $app.Id -Force -ErrorAction SilentlyContinue
    exit 1
}

Write-Host "Healthy. Logs: $Log / $LogErr" -ForegroundColor Green
try {
    Wait-Process -Id $app.Id
} finally {
    if (-not $app.HasExited) { Stop-Process -Id $app.Id -Force -ErrorAction SilentlyContinue }
}
