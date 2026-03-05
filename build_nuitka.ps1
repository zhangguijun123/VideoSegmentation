param(
    [string]$PythonExe = "python",
    [string]$FfmpegDir = $env:FFMPEG_DIR
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

& $PythonExe -m pip install --upgrade pip | Out-Null
& $PythonExe -m pip install --upgrade nuitka | Out-Null

$includeArgs = @(
    "--include-data-file=config.yaml=config.yaml",
    "--include-data-dir=data=data"
)

$cmd = @(
    "-m", "nuitka",
    "--standalone",
    "--follow-imports",
    "--assume-yes-for-downloads",
    "--output-dir=dist",
    "--remove-output",
    "--output-filename=VideoTool.exe",
    "main.py"
) + $includeArgs

& $PythonExe @cmd


$distDir = Join-Path $root "dist\VideoTool.dist"
if (-not (Test-Path $distDir)) {
    Write-Host "Output folder not found: $distDir" -ForegroundColor Yellow
    exit 0
}

if (-not $FfmpegDir) {
    $candidates = @(
        "D:\\Program Files\\ffmpeg-8.0.1-essentials_build\\ffmpeg-8.0.1-essentials_build\\bin",
        "C:\\ffmpeg\\bin"
    )
    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            $FfmpegDir = $candidate
            break
        }
    }
}

if ($FfmpegDir -and (Test-Path $FfmpegDir)) {
    $ffmpegExe = Join-Path $FfmpegDir "ffmpeg.exe"
    $ffprobeExe = Join-Path $FfmpegDir "ffprobe.exe"

    if (Test-Path $ffmpegExe) {
        Copy-Item $ffmpegExe $distDir -Force
    }
    if (Test-Path $ffprobeExe) {
        Copy-Item $ffprobeExe $distDir -Force
    }
} else {
    Write-Host "ffmpeg folder not found, skip copying ffmpeg/ffprobe." -ForegroundColor Yellow
}

Write-Host "Build done: $distDir" -ForegroundColor Green
