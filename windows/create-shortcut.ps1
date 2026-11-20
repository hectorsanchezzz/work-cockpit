# Creates a "Work Cockpit" shortcut on the Desktop (and Start menu) that runs open-cockpit.ps1.
$root = Split-Path $PSScriptRoot -Parent
$ps = (Get-Command powershell.exe).Source
$ws = New-Object -ComObject WScript.Shell
foreach ($dir in @([Environment]::GetFolderPath("Desktop"), (Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"))) {
    $lnk = $ws.CreateShortcut((Join-Path $dir "Work Cockpit.lnk"))
    $lnk.TargetPath = $ps
    $lnk.Arguments = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$root\windows\open-cockpit.ps1`""
    $lnk.WorkingDirectory = $root
    $lnk.Description = "Work Cockpit"
    $lnk.IconLocation = "$env:SystemRoot\System32\imageres.dll,109"
    $lnk.Save()
    Write-Output "Created $dir\Work Cockpit.lnk"
}
