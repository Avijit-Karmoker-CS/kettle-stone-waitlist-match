# Kettle & Stone Waitlist Match - one-time setup (Julie runs this once).
# It does three things on this computer only:
#   1. adds the "Waitlist Match" icon to the desktop
#   2. adds a Windows task that opens the morning list at 8:00 on weekdays
#   3. runs the self-check
# Nothing is downloaded and nothing is sent anywhere.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$pyw  = Join-Path $root "python\pythonw.exe"
$py   = Join-Path $root "python\python.exe"
$main = Join-Path $root "app\main.py"
$icon = Join-Path $root "app\waitlist_match\ui\icon.ico"

Write-Host ""
Write-Host "Setting up Waitlist Match in: $root"

# Files from a zip or USB can be marked as 'from the internet'. Clear that mark.
Get-ChildItem -Path $root -Recurse -File | Unblock-File -ErrorAction SilentlyContinue

if (-not (Test-Path $pyw)) { throw "The python folder is missing. Copy the whole Kettle & Stone Waitlist folder again." }

# 1. Desktop and Start menu icons
$shell = New-Object -ComObject WScript.Shell
foreach ($folder in @([Environment]::GetFolderPath("Desktop"), [Environment]::GetFolderPath("Programs"))) {
    $lnk = $shell.CreateShortcut((Join-Path $folder "Waitlist Match.lnk"))
    $lnk.TargetPath = $pyw
    $lnk.Arguments = "`"$main`""
    $lnk.WorkingDirectory = $root
    $lnk.IconLocation = $icon
    $lnk.Description = "Kettle & Stone Waitlist Match"
    $lnk.Save()
}
Write-Host "  - Desktop icon added: Waitlist Match"

# 2. Morning list at 8:00, Monday to Friday (runs later if the computer was off at 8:00)
try {
    $action   = New-ScheduledTaskAction -Execute $pyw -Argument "`"$main`" --morning" -WorkingDirectory $root
    $trigger  = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At 8:00am
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
    Register-ScheduledTask -TaskName "Waitlist Match - morning list" -Action $action -Trigger $trigger `
        -Settings $settings -Description "Opens the Kettle & Stone morning list at 8:00 on weekdays." -Force | Out-Null
    Write-Host "  - Morning list set for 8:00, Monday to Friday"
} catch {
    Write-Host "  - Could not add the 8:00 task ($($_.Exception.Message)). The program still works; open it from the desktop icon."
}

# 3. Self-check
Write-Host ""
Write-Host "Self-check:"
& $py $main --self-check
Write-Host ""
Write-Host "Done. Double-click 'Waitlist Match' on the desktop to start."
