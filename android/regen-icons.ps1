# regen-icons.ps1
# Regenerate Android launcher icons (5 dpis) AND adaptive icon foreground
# from a single source PNG.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File regen-icons.ps1
#   powershell -ExecutionPolicy Bypass -File regen-icons.ps1 -Source "path/to/icon.png"
#
# Default source: ..\assets\ic_flying_coin_source.png
# (relative to this script's android/ directory)

[CmdletBinding()]
param(
    [string]$Source
)

if (-not $Source) {
    $here = Split-Path -Parent $MyInvocation.MyCommand.Definition
    $candidate = Join-Path $here '..\assets\ic_flying_coin_source.png'
    if (Test-Path $candidate) {
        $Source = (Resolve-Path $candidate).Path
    } else {
        throw "Default source not found: $candidate. Pass -Source <path-to-png>."
    }
}

Add-Type -AssemblyName System.Drawing

$ErrorActionPreference = 'Stop'
$root = "$PSScriptRoot\app\src\main\res"
$sizes = @{
    mdpi    = 48
    hdpi    = 72
    xhdpi   = 96
    xxhdpi  = 144
    xxxhdpi = 192
}

if (-not (Test-Path $Source)) {
    throw "Source image not found: $Source"
}

# Adaptive icon foreground dimensions
# xxxhdpi (4x) baseline: 108dp canvas, 72dp safe area
$fgCanvas = 432
$fgSafe   = 288

Write-Host "Source: $Source"
$srcImg = [System.Drawing.Image]::FromFile($Source)
Write-Host "  $($srcImg.Width)x$($srcImg.Height)"

# --- 1) mipmap-* / ic_launcher.png ---
foreach ($name in $sizes.Keys) {
    $px = $sizes[$name]
    $bmp = New-Object System.Drawing.Bitmap $px, $px
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
    $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
    $g.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
    $g.DrawImage($srcImg, 0, 0, $px, $px)

    $dir = Join-Path $root ("mipmap-" + $name)
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
    $out = Join-Path $dir 'ic_launcher.png'
    $bmp.Save($out, [System.Drawing.Imaging.ImageFormat]::Png)

    Write-Host ("  mipmap-{0,-7} {1}x{1}  ({2:N0} bytes)" -f $name, $px, (Get-Item $out).Length)
    $g.Dispose()
    $bmp.Dispose()
}

# --- 2) drawable / ic_launcher_foreground.png (adaptive icon, xxxhdpi) ---
$fgBmp = New-Object System.Drawing.Bitmap $fgCanvas, $fgCanvas
$fgG = [System.Drawing.Graphics]::FromImage($fgBmp)
$fgG.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
$fgG.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
$fgG.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
$fgG.Clear([System.Drawing.Color]::Transparent)
$offset = ($fgCanvas - $fgSafe) / 2
$fgG.DrawImage($srcImg, $offset, $offset, $fgSafe, $fgSafe)

$drawableDir = Join-Path $root 'drawable'
if (-not (Test-Path $drawableDir)) { New-Item -ItemType Directory -Force -Path $drawableDir | Out-Null }
$fgOut = Join-Path $drawableDir 'ic_launcher_foreground.png'
$fgBmp.Save($fgOut, [System.Drawing.Imaging.ImageFormat]::Png)
Write-Host ("  drawable/ic_launcher_foreground.png {0}x{0}  ({1:N0} bytes)" -f $fgCanvas, (Get-Item $fgOut).Length)
$fgG.Dispose()
$fgBmp.Dispose()

$srcImg.Dispose()
Write-Host ""
Write-Host "All icons regenerated."
