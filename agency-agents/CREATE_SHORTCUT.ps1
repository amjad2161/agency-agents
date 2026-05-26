$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut("$env:USERPROFILE\Desktop\JARVIS.lnk")
$Shortcut.TargetPath  = "C:\Users\User\agency\JARVIS_OPEN.bat"
$Shortcut.WorkingDirectory = "C:\Users\User\agency"
$Shortcut.Description = "Open JARVIS GODSKILL Navigation System"
$Shortcut.WindowStyle = 1
$pyExe = "C:\Users\User\agency\.venv\Scripts\python.exe"
if (Test-Path $pyExe) {
    $Shortcut.IconLocation = "$pyExe,0"
} else {
    $Shortcut.IconLocation = "$env:SystemRoot\System32\imageres.dll,13"
}
$Shortcut.Save()
Write-Host "OK: $env:USERPROFILE\Desktop\JARVIS.lnk created"
