# Register a Windows scheduled task: run BeautyBrief daily at 07:30 (content = previous day).
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts/install_task.ps1
#   powershell -ExecutionPolicy Bypass -File scripts/install_task.ps1 -DryRun
# NOTE: keep this file ASCII-only. powershell.exe reads scripts as ANSI by default,
# so UTF-8 Chinese comments can break parsing.
param(
    [switch]$DryRun,
    [string]$Time = "07:30",
    [string]$TaskName = "BeautyBrief-0730"
)

$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$python = (Get-Command python).Source
$script = Join-Path $root "scripts\run_daily.py"

$arguments = "`"$script`""
if ($DryRun) { $arguments += " --dry-run" }

$action = New-ScheduledTaskAction -Execute $python -Argument $arguments
$trigger = New-ScheduledTaskTrigger -Daily -At $Time
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -DontStopOnIdleEnd -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

$old = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($old) { Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false }

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Description "BeautyBrief daily 07:30, content = previous day" | Out-Null

$t = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($t) {
    $info = Get-ScheduledTaskInfo -TaskName $TaskName
    Write-Host "OK: $($t.TaskName) state=$($t.State)"
    Write-Host "    exec : $($t.Actions[0].Execute)"
    Write-Host "    args : $($t.Actions[0].Arguments)"
    Write-Host "    start: $($t.Triggers[0].StartBoundary)"
    Write-Host "    next : $($info.NextRunTime)"
    Write-Host "Run now: schtasks /Run /TN $TaskName"
} else {
    Write-Host "FAILED: task not found after registration"
}
