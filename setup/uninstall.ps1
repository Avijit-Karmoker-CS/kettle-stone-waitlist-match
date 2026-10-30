# Removes the desktop icon and the 8:00 task. Does not touch the Data folder.
foreach ($folder in @([Environment]::GetFolderPath("Desktop"), [Environment]::GetFolderPath("Programs"))) {
    Remove-Item (Join-Path $folder "Waitlist Match.lnk") -ErrorAction SilentlyContinue
}
Unregister-ScheduledTask -TaskName "Waitlist Match - morning list" -Confirm:$false -ErrorAction SilentlyContinue
Write-Host "Icon and 8:00 task removed. You can now delete the program folder."
Write-Host "The Data folder holds the waitlist - keep a copy if you still need it."
