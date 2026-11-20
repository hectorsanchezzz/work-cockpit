# Opens the cockpit: starts the local server if it is not running, refreshes in the background
# when the data is older than 30 minutes, then opens the page in the default browser.
$root = Split-Path $PSScriptRoot -Parent
$env:PYTHONUTF8 = "1"
$env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
$py = if ($env:COCKPIT_PYTHON) { $env:COCKPIT_PYTHON } else { (Get-Command python -ErrorAction Stop).Source }
$pyw = Join-Path (Split-Path $py -Parent) "pythonw.exe"; if (-not (Test-Path $pyw)) { $pyw = $py }

$up = Test-NetConnection 127.0.0.1 -Port 8765 -InformationLevel Quiet -WarningAction SilentlyContinue
if (-not $up) { Start-Process $pyw -ArgumentList "`"$root\serve.py`"" -WorkingDirectory $root -WindowStyle Hidden; Start-Sleep 2 }

$page = Join-Path $root "out\index.html"
if (-not (Test-Path $page) -or ((Get-Date) - (Get-Item $page).LastWriteTime).TotalMinutes -gt 30) {
    Start-Process powershell -ArgumentList "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$root\run.ps1`"" -WindowStyle Hidden -Wait
}
Start-Process "http://127.0.0.1:8765/"
