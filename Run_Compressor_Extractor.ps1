$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $scriptDir

$conda = $null
$cmd = Get-Command conda -ErrorAction SilentlyContinue
if ($cmd) {
    $conda = $cmd.Source
} else {
    $candidates = @(
        Join-Path $env:USERPROFILE "anaconda3\Scripts\conda.exe",
        Join-Path $env:USERPROFILE "miniconda3\Scripts\conda.exe",
        "C:\ProgramData\anaconda3\Scripts\conda.exe"
    )
    foreach ($c in $candidates) {
        if (Test-Path $c) {
            $conda = $c
            break
        }
    }
}

if (-not $conda) {
    Write-Error "conda.exe not found. Please install or repair Anaconda/Miniconda."
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "Using conda: $conda"
& $conda run -n compressor python -m src.main
$exitCode = $LASTEXITCODE
if ($exitCode -ne 0) {
    Write-Error "Program exited with code $exitCode."
    Read-Host "Press Enter to exit"
    exit $exitCode
}
