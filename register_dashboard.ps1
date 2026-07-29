# Keeps the dashboard running. Registers a Task Scheduler job that
# starts the Dash server at logon; start it immediately with:
#   powershell -ExecutionPolicy Bypass -File register_dashboard.ps1
#   Start-ScheduledTask -TaskName PropensityLabDashboard
#
# The server listens on http://127.0.0.1:8050 and picks up each daily
# refresh on its own; it never needs a restart for new data.

$taskName = "PropensityLabDashboard"
$projectDir = $PSScriptRoot

$uv = (Get-Command uv -ErrorAction SilentlyContinue).Source
if (-not $uv) {
    Write-Error "uv was not found on PATH. Install it first: https://docs.astral.sh/uv/"
    exit 1
}

$action = New-ScheduledTaskAction `
    -Execute $uv `
    -Argument "run python app/app.py" `
    -WorkingDirectory $projectDir

$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -DontStopOnIdleEnd `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Days 3650)

Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Propensity Lab dashboard server on http://127.0.0.1:8050." | Out-Null

Write-Host "Registered '$taskName' (starts at logon, auto-restarts on failure)."
Write-Host "Start it now:  Start-ScheduledTask -TaskName $taskName"
