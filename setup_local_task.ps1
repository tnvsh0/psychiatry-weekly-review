# setup_local_task.ps1
# Registers a Windows Scheduled Task that runs the weekly psychiatry review
# every Sunday at 09:00 Israel time (06:00 UTC in summer / 07:00 UTC in winter).
#
# Run this ONCE as Administrator, from the repo root:
#   Right-click setup_local_task.ps1 -> "Run as Administrator"
#
# The task will:
#   - Fire every Sunday at 09:00 local time
#   - Wake the PC from sleep if it is sleeping
#   - Run for up to 3 hours before timing out
#   - Log to logs\run_YYYY-MM-DD_HH-mm.log in the repo folder

$ErrorActionPreference = "Stop"

$TaskName  = "PsychiatryWeeklyReview"
$RepoRoot  = Split-Path -Parent $MyInvocation.MyCommand.Path
$Script    = Join-Path $RepoRoot "run_weekly.ps1"

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  Psychiatry Weekly Review — Task Setup" -ForegroundColor Cyan
Write-Host "  Repo : $RepoRoot" -ForegroundColor Cyan
Write-Host "  Task : $TaskName" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

if (-not (Test-Path $Script)) {
    Write-Error "run_weekly.ps1 not found at: $Script"
}

# Remove existing task if present
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Write-Host "Removing existing task..." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

# Action: run PowerShell with run_weekly.ps1
$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NonInteractive -ExecutionPolicy Bypass -File `"$Script`""

# Trigger: every Sunday at 09:00 local time
$trigger = New-ScheduledTaskTrigger `
    -Weekly `
    -DaysOfWeek Sunday `
    -At "09:00AM"

# Settings: wake from sleep, up to 3 hours, run whether or not user is logged on
$settings = New-ScheduledTaskSettingsSet `
    -WakeToRun `
    -ExecutionTimeLimit (New-TimeSpan -Hours 3) `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable `
    -MultipleInstances IgnoreNew

# Register as current user (elevated)
Register-ScheduledTask `
    -TaskName  $TaskName `
    -Action    $action `
    -Trigger   $trigger `
    -Settings  $settings `
    -RunLevel  Highest `
    -Force | Out-Null

# Enable wake timers in Windows power settings (required for WakeToRun to work)
Write-Host "Enabling wake timers in power settings..." -ForegroundColor Yellow
powercfg /setacvalueindex SCHEME_CURRENT SUB_SLEEP RTCWAKE 1
powercfg /setactive SCHEME_CURRENT
Write-Host "  Wake timers enabled." -ForegroundColor Green

Write-Host ""
Write-Host "==========================================" -ForegroundColor Green
Write-Host "  Task registered successfully!" -ForegroundColor Green
Write-Host ""
Write-Host "  Next run: Sunday 09:00 local time" -ForegroundColor White
Write-Host "  The PC will wake from sleep automatically." -ForegroundColor White
Write-Host ""
Write-Host "  Test manually right now:" -ForegroundColor White
Write-Host "  Start-ScheduledTask -TaskName '$TaskName'" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Check task status:" -ForegroundColor White
Write-Host "  Get-ScheduledTask -TaskName '$TaskName' | Get-ScheduledTaskInfo" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Green
Write-Host ""
Write-Host "IMPORTANT: Also enable wake timers in your PC BIOS/UEFI if the PC" -ForegroundColor Yellow
Write-Host "does not wake from sleep after registering the task." -ForegroundColor Yellow
