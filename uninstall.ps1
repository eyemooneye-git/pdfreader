# Remove registry traces left by older pdfreader builds and, optionally, the
# portable exe plus its local settings.
#
# Current builds never write to the registry: configuration lives in
# %LOCALAPPDATA%\pdfreader\pdfreader.ini.  This script only cleans up entries
# created by older versions, or by Explorer "Open with" using this exe.
#
#   powershell -ExecutionPolicy Bypass -File uninstall.ps1
#   powershell -ExecutionPolicy Bypass -File uninstall.ps1 -RemoveFiles
#
# No administrator rights are required: everything lives under HKCU.

param(
    [switch]$RemoveFiles
)

$ErrorActionPreference = "Stop"
$exe = Join-Path $PSScriptRoot "pdfreader.exe"
$config = Join-Path $env:LOCALAPPDATA "pdfreader"

Write-Host "Removing registry traces left by older pdfreader versions..."

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

$values = @(
    @{ Path = "HKCU:\Software\Classes\.pdf\OpenWithProgids"; Name = "PDFReader.pdf" },
    @{ Path = "HKCU:\Software\Classes\.pdf\OpenWithList"; Name = "pdfreader.exe" },
    @{ Path = "HKCU:\Software\RegisteredApplications"; Name = "pdfreader" }
)
foreach ($item in $values) {
    if (Test-Path $item.Path) {
        Remove-ItemProperty -Path $item.Path -Name $item.Name -ErrorAction SilentlyContinue
        Write-Host "  cleared $($item.Path)\$($item.Name)"
    }
}

# "Open with" stores the exe as extra values (a, b, c...) plus an MRUList index.
$fileExt = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\.pdf"
$openWithList = "$fileExt\OpenWithList"
if (Test-Path $openWithList) {
    $removed = @()
    $props = Get-ItemProperty -Path $openWithList
    foreach ($prop in $props.PSObject.Properties) {
        if ($prop.Name -in @("PSPath", "PSParentPath", "PSChildName", "PSDrive", "PSProvider")) { continue }
        if ($prop.Name -eq "MRUList") { continue }
        if ("$($prop.Value)" -like "*pdfreader*") {
            Remove-ItemProperty -Path $openWithList -Name $prop.Name -ErrorAction SilentlyContinue
            $removed += $prop.Name
            Write-Host "  cleared $openWithList\$($prop.Name)"
        }
    }
    if ($removed.Count -gt 0) {
        $mru = (Get-ItemProperty -Path $openWithList -Name MRUList -ErrorAction SilentlyContinue).MRUList
        if ($mru) {
            $kept = ($mru.ToCharArray() | Where-Object { $removed -notcontains [string]$_ }) -join ""
            Set-ItemProperty -Path $openWithList -Name MRUList -Value $kept
            Write-Host "  updated MRUList to '$kept'"
        }
    }
}

# Windows 11 mirrors the last chosen handler here while the ProgID existed.
$userChoiceLatest = "$fileExt\UserChoiceLatest"
if (Test-Path $userChoiceLatest) {
    $progId = (Get-ItemProperty -Path "$userChoiceLatest\ProgId" -Name ProgId -ErrorAction SilentlyContinue).ProgId
    if ("$progId" -like "*pdfreader*") {
        Remove-Item $userChoiceLatest -Recurse -Force
        Write-Host "  removed $userChoiceLatest"
    }
}

Write-Host "Registry cleanup finished."

if ($RemoveFiles) {
    if (Test-Path $exe) {
        Remove-Item $exe -Force
        Write-Host "Deleted $exe"
    }
    if (Test-Path $config) {
        Remove-Item $config -Recurse -Force
        Write-Host "Deleted $config"
    }
    Write-Host "You can now delete the whole pdfreader folder if you want."
} else {
    Write-Host "pdfreader.exe and $config were kept. Run with -RemoveFiles to delete them too."
}
