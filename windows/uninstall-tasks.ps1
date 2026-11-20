foreach ($n in "Cockpit refresh", "Cockpit server") {
    Stop-ScheduledTask -TaskName $n -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $n -Confirm:$false -ErrorAction SilentlyContinue
}
Write-Output "Removed the Cockpit scheduled tasks."
