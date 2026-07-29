# Registers the daily refresh with Windows Task Scheduler.
# Run once from an elevated or normal PowerShell prompt:
#   powershell -ExecutionPolicy Bypass -File register_task.ps1
#
# The job runs every morning at 06:30 local time. If the machine is
# asleep at that moment, the task fires as soon as it wakes.

$taskName = "NextProductDailyRefresh"
$projectDir = $PSScriptRoot

$uv = (Get-Command uv -ErrorAction SilentlyContinue).Source
if (-not $uv) {
    Write-Error "uv was not found on PATH. Install it first: https://docs.astral.sh/uv/"
    exit 1
}

$action = New-ScheduledTaskAction `
    -Execute $uv `
    -Argument "run python scheduler.py" `
    -WorkingDirectory $projectDir

$trigger = New-ScheduledTaskTrigger -Daily -At 6:30am

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -DontStopOnIdleEnd `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1)

Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Daily refresh: ingest next snapshot, rebuild dbt models, retrain and rescore." | Out-Null

Write-Host "Registered '$taskName' (daily at 06:30)."
Write-Host "Run it now to test:  Start-ScheduledTask -TaskName $taskName"
