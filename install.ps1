#Requires -Version 5.1
<#
.SYNOPSIS
  Registers a per-user Explorer context menu: Host on web server (port 5000)
#>
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$hostCmd = Join-Path $root "host.cmd"
$script = Join-Path $root "host_file.py"

if (-not (Test-Path -LiteralPath $hostCmd)) { throw "Missing host.cmd at $hostCmd" }
if (-not (Test-Path -LiteralPath $script)) { throw "Missing host_file.py at $script" }

# .reg string rules: backslash -> \\ , quote -> \"
function Escape-RegString([string]$s) {
    return ($s -replace '\\', '\\' -replace '"', '\"')
}

$command = "`"$hostCmd`" `"%1`""
$cmdReg = Escape-RegString $command

$regFile = Join-Path $env:TEMP "host-on-5000-install.reg"
$regContent = @"
Windows Registry Editor Version 5.00

[HKEY_CURRENT_USER\Software\Classes\*\shell\HostOn5000]
@="Host on web server (port 5000)"
"Icon"="shell32.dll,13"

[HKEY_CURRENT_USER\Software\Classes\*\shell\HostOn5000\command]
@="$cmdReg"
"@

Set-Content -LiteralPath $regFile -Value $regContent -Encoding Unicode
$p = Start-Process -FilePath "reg.exe" -ArgumentList @("import", $regFile) -Wait -PassThru -NoNewWindow
Remove-Item -LiteralPath $regFile -Force -ErrorAction SilentlyContinue

if ($p.ExitCode -ne 0) {
    throw "reg import failed with exit code $($p.ExitCode)"
}

# Verify
$verify = & reg.exe query "HKCU\Software\Classes\*\shell\HostOn5000\command" /ve 2>&1 | Out-String
if ($verify -notmatch "host\.cmd") {
    throw "Registry command value was not set correctly:`n$verify"
}

Write-Host "Installed context menu for current user."
Write-Host "  Menu:  Host on web server (port 5000)"
Write-Host "  Runs:  $command"
Write-Host ""
Write-Host "Right-click any file in Explorer to use it."
Write-Host "Uninstall with: .\uninstall.ps1"
