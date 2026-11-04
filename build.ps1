# Build pdfreader.exe and (optionally) register the file association.
#
#   powershell -ExecutionPolicy Bypass -File build.ps1
#   powershell -ExecutionPolicy Bypass -File build.ps1 -SkipInstall -Register
#
# The build is a single self-contained exe. PySide6 makes it fairly large
# (~56 MB); that is expected for a one-file Qt application.

param(
    [switch]$SkipInstall,
    [switch]$Register,
    [switch]$SkipIcon
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "[1/5] Python environment"
python --version

if (-not $SkipInstall) {
    Write-Host "[2/5] Installing dependencies"
    python -m pip install --disable-pip-version-check -r requirements.txt
} else {
    Write-Host "[2/5] Skipping pip install"
}

Write-Host "[3/5] Sample PDF and icon"
python tools\make_sample_pdf.py
if (-not $SkipIcon) {
    powershell -NoProfile -ExecutionPolicy Bypass -File tools\make_icon.ps1
}

Write-Host "[4/5] PyInstaller"
python -m PyInstaller --noconfirm --clean pdfreader.spec
if (-not (Test-Path "dist\pdfreader.exe")) {
    throw "PyInstaller did not produce dist\pdfreader.exe"
}

Copy-Item "dist\pdfreader.exe" ".\pdfreader.exe" -Force
$size = (Get-Item ".\pdfreader.exe").Length / 1MB
Write-Host ("[5/5] Wrote {0}\pdfreader.exe ({1:N1} MB)" -f $PSScriptRoot, $size)

if ($Register) {
    Write-Host "Registering file association for the current user..."
    $process = Start-Process -FilePath (Join-Path $PSScriptRoot "pdfreader.exe") `
        -ArgumentList "--register" -Wait -PassThru
    if ($process.ExitCode -ne 0) {
        throw "Registration failed with exit code $($process.ExitCode)"
    }
    Write-Host "Registered. Right-click a PDF -> Open with -> pdfreader."
}
