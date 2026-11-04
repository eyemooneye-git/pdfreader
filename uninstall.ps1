# Remove everything pdfreader added to HKCU (file associations, Open With entry,
# Default Apps capabilities). Optionally delete the portable exe itself.
#
#   powershell -ExecutionPolicy Bypass -File uninstall.ps1
#   powershell -ExecutionPolicy Bypass -File uninstall.ps1 -RemoveFiles
#
# No administrator rights are required: each user has their own HKCU entries.
# Removing the association never touches .pdf files.

param(
    [switch]$RemoveFiles
)

$ErrorActionPreference = "Stop"
$exe = Join-Path $PSScriptRoot "pdfreader.exe"

Write-Host "Removing pdfreader registry entries (current user)..."

if (Test-Path $exe) {
    $process = Start-Process -FilePath $exe -ArgumentList "--unregister" -Wait -PassThru
    if ($process.ExitCode -ne 0) {
        Write-Warning "pdfreader.exe --unregister returned $($process.ExitCode); falling back to direct cleanup."
    }
}

# Belt and braces: remove keys even if the exe has already been deleted.
$keys = @(
    "HKCU:\Software\Classes\PDFReader.pdf",
    "HKCU:\Software\Classes\Applications\pdfreader.exe",
    "HKCU:\Software\PDFReader",
    "HKCU:\Software\pdfreader"
)
foreach ($key in $keys) {
    if (Test-Path $key) {
        Remove-Item $key -Recurse -Force
        Write-Host "  removed $key"
    }
}

$openWith = "HKCU:\Software\Classes\.pdf\OpenWithProgids"
if (Test-Path $openWith) {
    Remove-ItemProperty -Path $openWith -Name "PDFReader.pdf" -ErrorAction SilentlyContinue
}
$openWithList = "HKCU:\Software\Classes\.pdf\OpenWithList"
if (Test-Path $openWithList) {
    Remove-ItemProperty -Path $openWithList -Name "pdfreader.exe" -ErrorAction SilentlyContinue
}
$registered = "HKCU:\Software\RegisteredApplications"
if (Test-Path $registered) {
    Remove-ItemProperty -Path $registered -Name "pdfreader" -ErrorAction SilentlyContinue
}

Write-Host "Registry cleanup finished."

if ($RemoveFiles) {
    if (Test-Path $exe) {
        Remove-Item $exe -Force
        Write-Host "Deleted $exe"
    }
    Write-Host "You can now delete the whole pdfreader folder if you want."
} else {
    Write-Host "pdfreader.exe was kept. Run with -RemoveFiles to delete it too."
}
