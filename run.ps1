# Refresh the cockpit: collect local sources, fetch Linear, the enabled test sources (extras.py), render
# (v2 data and summary, then the live D page), build the local page.
# Run by Task Scheduler (Cockpit refresh) every 30 minutes, or by hand: powershell -File run.ps1
# Read-only towards every source.
$ErrorActionPreference = "Continue"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
Set-Location $PSScriptRoot
# Pick up programs installed after this session started (gh, python): reload PATH from the registry.
$env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")

$py = if ($env:COCKPIT_PYTHON) { $env:COCKPIT_PYTHON } else { "python" }
$lock = Join-Path ([System.IO.Path]::GetTempPath()) "cockpit-refresh.lock"

# Same lock as serve.py (a directory in the temp folder). A lock older than 15 minutes is a crashed run.
if (Test-Path $lock) {
    if (((Get-Date) - (Get-Item $lock).LastWriteTime).TotalMinutes -gt 15) { Remove-Item $lock -Force -Recurse }
    else { Write-Output "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') already running, skipped"; exit 0 }
}
New-Item -ItemType Directory -Path $lock -ErrorAction Stop | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $PSScriptRoot "logs"), (Join-Path $PSScriptRoot "data") | Out-Null

try {
    Write-Output "== $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') refresh"
    & $py collect.py;      if ($LASTEXITCODE) { Write-Output "collect.py failed" }
    & $py linear_fetch.py
    & $py extras.py;       if ($LASTEXITCODE) { Write-Output "extras.py failed" }
    & $py render_v2.py;    if ($LASTEXITCODE) { exit 1 }
    & $py proposals.py --live; if ($LASTEXITCODE) { Write-Output "proposals.py --live failed, serving v2" }
    & $py build_local.py
}
finally {
    Remove-Item $lock -Force -Recurse -ErrorAction SilentlyContinue
}
