# Build assets/pdfreader.ico from vector shapes so the exe icon, Explorer icon
# and window icon all share exactly the same artwork.
#
# Run from anywhere:
#   powershell -ExecutionPolicy Bypass -File tools\make_icon.ps1
#
# Transparent background, white document sheet, folded corner and a red PDF
# band.  The red band is an original "PDF" mark, not the Adobe logo.

Add-Type -AssemblyName System.Drawing

$root = Split-Path $PSScriptRoot -Parent
$assets = Join-Path $root "assets"
New-Item -ItemType Directory -Force -Path $assets | Out-Null

function New-PagePath {
    # A4-ish sheet with the top-right corner folded away.
    $path = New-Object System.Drawing.Drawing2D.GraphicsPath
    $r = 34.0
    $d = $r * 2
    $left = 188.0
    $right = 836.0
    $top = 88.0
    $bottom = 936.0
    $fold = 154.0

    $path.AddLine($left + $r, $top, $right - $fold, $top)
    $path.AddLine($right - $fold, $top, $right, $top + $fold)
    $path.AddLine($right, $top + $fold, $right, $bottom - $r)
    $path.AddArc($right - $d, $bottom - $d, $d, $d, 0, 90)
    $path.AddLine($right - $r, $bottom, $left + $r, $bottom)
    $path.AddArc($left, $bottom - $d, $d, $d, 90, 90)
    $path.AddLine($left, $bottom - $r, $left, $top + $r)
    $path.AddArc($left, $top, $d, $d, 180, 90)
    $path.CloseFigure()
    return $path
}

function Draw-Icon([int]$size) {
    $bmp = New-Object System.Drawing.Bitmap($size, $size, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $g.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
    $g.CompositingQuality = [System.Drawing.Drawing2D.CompositingQuality]::HighQuality
    $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
    $g.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAliasGridFit
    $g.Clear([System.Drawing.Color]::Transparent)
    $g.ScaleTransform($size / 1024.0, $size / 1024.0)

    $page = New-PagePath

    # Soft shadow keeps the white page visible on a light Explorer background.
    $shadow = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(46, 15, 23, 42))
    $state = $g.Save()
    $g.TranslateTransform(0, 22)
    $g.FillPath($shadow, $page)
    $g.Restore($state)
    $shadow.Dispose()

    # Sheet.
    $paper = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(255, 250, 252, 255))
    $g.FillPath($paper, $page)
    $paper.Dispose()

    $outline = New-Object System.Drawing.Pen([System.Drawing.Color]::FromArgb(255, 100, 116, 139), 9)
    $outline.LineJoin = [System.Drawing.Drawing2D.LineJoin]::Round
    $g.DrawPath($outline, $page)

    # Folded top-right corner.
    $fold = New-Object System.Drawing.Drawing2D.GraphicsPath
    $fold.AddPolygon(@(
        (New-Object System.Drawing.PointF(682, 88)),
        (New-Object System.Drawing.PointF(836, 242)),
        (New-Object System.Drawing.PointF(682, 242))
    ))
    $foldBrush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(255, 226, 232, 240))
    $g.FillPath($foldBrush, $fold)
    $g.DrawPath($outline, $fold)
    $foldBrush.Dispose()
    $fold.Dispose()
    $outline.Dispose()

    # Text lines on the sheet.
    $lineBrush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(255, 148, 163, 184))
    $g.FillRectangle($lineBrush, 280, 352, 430, 26)
    $g.FillRectangle($lineBrush, 280, 422, 430, 26)
    $g.FillRectangle($lineBrush, 280, 492, 300, 26)
    $lineBrush.Dispose()

    # Red PDF band, clipped to the rounded sheet.
    $oldClip = $g.Clip
    $g.SetClip($page)
    $red = New-Object System.Drawing.Drawing2D.LinearGradientBrush(
        (New-Object System.Drawing.RectangleF(0, 690, 1024, 190)),
        [System.Drawing.Color]::FromArgb(255, 239, 68, 68),
        [System.Drawing.Color]::FromArgb(255, 185, 28, 28),
        [System.Drawing.Drawing2D.LinearGradientMode]::Vertical)
    $g.FillRectangle($red, 188, 690, 648, 190)
    $red.Dispose()
    $g.Clip = $oldClip

    # "PDF" in white, optically centred in the band.
    $font = New-Object System.Drawing.Font("Segoe UI", 108, [System.Drawing.FontStyle]::Bold, [System.Drawing.GraphicsUnit]::Pixel)
    $fmt = New-Object System.Drawing.StringFormat
    $fmt.Alignment = [System.Drawing.StringAlignment]::Center
    $fmt.LineAlignment = [System.Drawing.StringAlignment]::Center
    $textBrush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::White)
    $g.DrawString("PDF", $font, $textBrush, (New-Object System.Drawing.RectangleF(188, 690, 648, 190)), $fmt)
    $textBrush.Dispose()
    $fmt.Dispose()
    $font.Dispose()

    $page.Dispose()
    $g.Dispose()
    return $bmp
}

function Get-DibBytes([System.Drawing.Bitmap]$bmp) {
    $size = $bmp.Width
    $xor = New-Object byte[] ($size * $size * 4)
    for ($y = 0; $y -lt $size; $y++) {
        for ($x = 0; $x -lt $size; $x++) {
            $c = $bmp.GetPixel($x, $size - 1 - $y)
            $i = ($y * $size + $x) * 4
            $xor[$i] = $c.B
            $xor[$i + 1] = $c.G
            $xor[$i + 2] = $c.R
            $xor[$i + 3] = $c.A
        }
    }

    $maskRow = [int]([math]::Ceiling($size / 32.0) * 4)
    $mask = New-Object byte[] ($maskRow * $size)

    $ms = New-Object System.IO.MemoryStream
    $bw = New-Object System.IO.BinaryWriter($ms)
    $bw.Write([uint32]40)
    $bw.Write([int32]$size)
    $bw.Write([int32]($size * 2))
    $bw.Write([uint16]1)
    $bw.Write([uint16]32)
    $bw.Write([uint32]0)
    $bw.Write([uint32]($xor.Length + $mask.Length))
    $bw.Write([int32]0)
    $bw.Write([int32]0)
    $bw.Write([uint32]0)
    $bw.Write([uint32]0)
    $bw.Write($xor)
    $bw.Write($mask)
    $bw.Flush()
    $result = $ms.ToArray()
    $bw.Dispose()
    $ms.Dispose()
    return ,$result
}

$sizes = @(16, 20, 24, 32, 40, 48, 64, 128, 256)
$images = @()

foreach ($size in $sizes) {
    $bmp = Draw-Icon $size
    # PNG entries keep the 128/256 px frames compact; smaller sizes stay as
    # classic DIBs for maximum compatibility in the title bar and Explorer.
    if ($size -ge 128) {
        $ms = New-Object System.IO.MemoryStream
        $bmp.Save($ms, [System.Drawing.Imaging.ImageFormat]::Png)
        $bytes = $ms.ToArray()
        $ms.Dispose()
    } else {
        $bytes = Get-DibBytes $bmp
    }
    if ($size -eq 256) {
        $bmp.Save((Join-Path $assets "pdfreader.png"), [System.Drawing.Imaging.ImageFormat]::Png)
    }
    $bmp.Dispose()
    $images += [pscustomobject]@{ Size = $size; Bytes = $bytes }
}

$icoPath = Join-Path $assets "pdfreader.ico"
$out = New-Object System.IO.MemoryStream
$bw = New-Object System.IO.BinaryWriter($out)
$bw.Write([uint16]0)
$bw.Write([uint16]1)
$bw.Write([uint16]$images.Count)

$offset = 6 + 16 * $images.Count
foreach ($image in $images) {
    $dim = if ($image.Size -eq 256) { 0 } else { $image.Size }
    $bw.Write([byte]$dim)
    $bw.Write([byte]$dim)
    $bw.Write([byte]0)
    $bw.Write([byte]0)
    $bw.Write([uint16]1)
    $bw.Write([uint16]32)
    $bw.Write([uint32]$image.Bytes.Length)
    $bw.Write([uint32]$offset)
    $offset += $image.Bytes.Length
}
foreach ($image in $images) {
    $bw.Write([byte[]]$image.Bytes)
}
$bw.Flush()
[System.IO.File]::WriteAllBytes($icoPath, $out.ToArray())
$bw.Dispose()
$out.Dispose()

Write-Output "Wrote $icoPath ($((Get-Item $icoPath).Length) bytes)"
