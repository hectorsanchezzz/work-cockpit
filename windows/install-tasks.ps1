# Registers two per-user scheduled tasks (no admin needed):
#   Cockpit refresh : at logon, then every 30 minutes, runs run.ps1
#   Cockpit server  : at logon, runs serve.py on http://127.0.0.1:8765/ (localhost only)
# Remove with: windows\uninstall-tasks.ps1
$root = Split-Path $PSScriptRoot -Parent
$py = if ($env:COCKPIT_PYTHON) { $env:COCKPIT_PYTHON } else { (Get-Command python -ErrorAction Stop).Source }
$pyw = Join-Path (Split-Path $py -Parent) "pythonw.exe"   # no console window
if (-not (Test-Path $pyw)) { $pyw = $py }
$user = "$env:USERDOMAIN\$env:USERNAME"
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 1)

$refresh = New-ScheduledTaskAction -Execute "powershell.exe" -WorkingDirectory $root `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -Command `"& '$root\run.ps1' *>> '$root\logs\refresh.log'`""
$t1 = New-ScheduledTaskTrigger -AtLogOn -User $user
$t2 = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 30)
New-Item -ItemType Directory -Force -Path "$root\logs" | Out-Null
Register-ScheduledTask -TaskName "Cockpit refresh" -Action $refresh -Trigger @($t1, $t2) -Settings $settings -Force | Out-Null

$serve = New-ScheduledTaskAction -Execute $pyw -Argument "`"$root\serve.py`"" -WorkingDirectory $root
$settings2 = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName "Cockpit server" -Action $serve -Trigger $t1 -Settings $settings2 -Force | Out-Null

Write-Output "Registered 'Cockpit refresh' and 'Cockpit server'. Start now: Start-ScheduledTask 'Cockpit server'; Start-ScheduledTask 'Cockpit refresh'"
