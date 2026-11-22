<#
.SYNOPSIS
    Run the Codex PoC demo.
.DESCRIPTION
    Orchestrates building the codex binary, installing Python dependencies,
    and running the PoC demo that drives app-server via the Python SDK.
.PARAMETER SkipBuild
    Skip the cargo build step (use existing binary).
.PARAMETER Model
    Override the model name (default: qwen3.7-plus or $env:CODEX_MODEL).
#>
param(
    [switch]$SkipBuild,
    [string]$Model
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PoCRoot = Resolve-Path $ScriptDir
$MetaHarnessRoot = Resolve-Path (Join-Path $PoCRoot "..")
$CodexRustDir = Join-Path (Join-Path $MetaHarnessRoot "..") "codex-rust-v0.155.1\codex-rs"

Write-Host "=== Codex PoC Runner ===" -ForegroundColor Cyan
Write-Host ""

# Load .env file if present
$envFile = Join-Path $PoCRoot ".env"
if (Test-Path $envFile) {
    Write-Host "Loading .env file..." -ForegroundColor Gray
    Get-Content $envFile | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
            $key, $value = $line.Split("=", 2)
            $key = $key.Trim()
            $value = $value.Trim()
            if ($key -and -not [Environment]::GetEnvironmentVariable($key, "Process")) {
                [Environment]::SetEnvironmentVariable($key, $value, "Process")
            }
        }
    }
}

# Check prerequisites
Write-Host "[Check] Prerequisites..." -ForegroundColor Yellow

# Python
try {
    $pyVersion = python --version 2>&1
    Write-Host "  Python: $pyVersion"
} catch {
    Write-Error "Python not found. Install Python 3.10+ from https://python.org"
    exit 1
}

# Pydantic
$hasPydantic = python -c "import pydantic; print(pydantic.__version__)" 2>$null
if (-not $hasPydantic) {
    Write-Host "  Installing pydantic..." -ForegroundColor Yellow
    python -m pip install pydantic 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to install pydantic. Run: pip install pydantic"
        exit 1
    }
}
Write-Host "  pydantic: $($hasPydantic.Trim())"

# Build binary if needed
if (-not $SkipBuild) {
    Write-Host ""
    Write-Host "[Build] Building codex binary..." -ForegroundColor Yellow
    & (Join-Path $PoCRoot "build.ps1")
    if ($LASTEXITCODE -ne 0) { exit 1 }
} else {
    Write-Host "  Skipping build (--SkipBuild)" -ForegroundColor Gray
}

# Set model override
if ($Model) {
    $env:CODEX_MODEL = $Model
    Write-Host "  Model override: $Model"
}

# Run PoC
Write-Host ""
Write-Host "[Run] Starting PoC demo..." -ForegroundColor Yellow
Write-Host "----------------------------------------" -ForegroundColor Gray

# Add SDK source to Python path and run
$SdkSrc = Join-Path (Join-Path $MetaHarnessRoot "..") "codex-rust-v0.155.1\sdk\python\src"
$SdkSrc = Resolve-Path $SdkSrc

$env:PYTHONPATH = "$SdkSrc;$env:PYTHONPATH"
$env:CODEX_POC_ROOT = $PoCRoot

python (Join-Path $PoCRoot "poc_demo.py")
$exitCode = $LASTEXITCODE

Write-Host "----------------------------------------" -ForegroundColor Gray
if ($exitCode -eq 0) {
    Write-Host "`n✓ PoC completed successfully!" -ForegroundColor Green
} else {
    Write-Host "`n✗ PoC failed with exit code $exitCode" -ForegroundColor Red
}
exit $exitCode