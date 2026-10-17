# ELION (JARVIS) Windows Management CLI (PowerShell)
param(
    [Parameter(Position=0)]
    [string]$Command = "status",
    [Parameter(Position=1)]
    [string]$Action = "status",
    [switch]$Foreground,
    [switch]$TaskScheduler,
    [int]$Port = 8080
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

$venvPython = Join-Path $scriptDir ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    $venvPython = (Get-Command python -ErrorAction SilentlyContinue).Source
    if (-not $venvPython) {
        Write-Error "[ERROR] Virtual environment .venv was not found. Please run setup.bat or setup.ps1 first."
        exit 1
    }
}

$launcherScript = Join-Path $scriptDir "src\launcher.py"

$extraArgs = @()
if ($Foreground) { $extraArgs += "--foreground" }
if ($TaskScheduler) { $extraArgs += "--task-scheduler" }
if ($Port -ne 8080) { $extraArgs += @("--port", $Port) }

if ($Command -eq "autostart") {
    & $venvPython $launcherScript autostart $Action @extraArgs
} else {
    & $venvPython $launcherScript $Command @extraArgs
}
