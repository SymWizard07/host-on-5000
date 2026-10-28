#Requires -Version 5.1
$ErrorActionPreference = "Stop"

$regFile = Join-Path $env:TEMP "host-on-5000-uninstall.reg"
$regContent = @"
Windows Registry Editor Version 5.00

[-HKEY_CURRENT_USER\Software\Classes\*\shell\HostOn5000]
"@
Set-Content -LiteralPath $regFile -Value $regContent -Encoding Unicode
$p = Start-Process -FilePath "reg.exe" -ArgumentList @("import", $regFile) -Wait -PassThru -NoNewWindow
Remove-Item -LiteralPath $regFile -Force -ErrorAction SilentlyContinue

if ($p.ExitCode -ne 0) {
    Write-Host "Registry remove returned exit code $($p.ExitCode) (may already be uninstalled)."
} else {
    Write-Host "Removed context menu HostOn5000."
}

# Stop a running host if present
$pidFile = Join-Path $env:LOCALAPPDATA "host-on-5000\current.pid"
if (Test-Path -LiteralPath $pidFile) {
    $procId = (Get-Content -LiteralPath $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1).Trim()
    if ($procId -match '^\d+$') {
        taskkill /PID $procId /T /F 2>$null | Out-Null
        Write-Host "Stopped running host PID $procId."
    }
    Remove-Item -LiteralPath (Join-Path $env:LOCALAPPDATA "host-on-5000") -Recurse -Force -ErrorAction SilentlyContinue
}
