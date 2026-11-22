<#
.SYNOPSIS
    Build the Codex CLI binary from local source.
.DESCRIPTION
    Locates the codex-rs workspace relative to this script and runs
    `cargo build --bin codex` producing a debug binary.
#>
param(
    [switch]$Release
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Resolve paths relative to the PoC directory
$PoCRoot = Resolve-Path $ScriptDir
$MetaHarnessRoot = Resolve-Path (Join-Path $PoCRoot "..")
$CodexRustDir = Join-Path (Join-Path $MetaHarnessRoot "..") "codex-rust-v0.155.1\codex-rs"

if (-not (Test-Path $CodexRustDir)) {
    Write-Error "codex-rs directory not found at: $CodexRustDir"
    Write-Error "Expected layout: meta-harness/codex-rust-v0.155.1/codex-rs/"
    exit 1
}

$CodexRustDir = Resolve-Path $CodexRustDir
Write-Host "=== Codex Build ===" -ForegroundColor Cyan
Write-Host "Workspace: $CodexRustDir"

# Check Rust toolchain
try {
    $rustcVersion = rustc --version
    Write-Host "Rust:      $rustcVersion"
} catch {
    Write-Error "Rust toolchain not found. Install from https://rustup.rs"
    exit 1
}

# Add MinGW to PATH (required for GNU toolchain on Windows)
$mingwBin = "C:\Users\Wei.Wang\mingw64\mingw64\bin"
if (Test-Path $mingwBin) {
    $env:Path = "$mingwBin;$env:Path"
    Write-Host "MinGW:     $mingwBin"
} else {
    Write-Warning "MinGW not found at $mingwBin — GNU toolchain may fail"
}

# Build
Push-Location $CodexRustDir
try {
    $profile = if ($Release) { "--release" } else { "" }
    Write-Host "Building codex binary..." -ForegroundColor Yellow
    Write-Host "Command: cargo build --bin codex $profile"
    Write-Host "(First build may take 5-15 minutes. Subsequent builds use cached artifacts.)"

    $buildArgs = @("build", "--bin", "codex")
    if ($Release) {
        $buildArgs += "--release"
    }

    $result = cargo @buildArgs 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Cargo build failed:"
        Write-Error ($result -join "`n")
        exit 1
    }

    $targetDir = if ($Release) { "release" } else { "debug" }
    $binary = if ($IsWindows -or $env:OS -eq "Windows_NT") {
        Join-Path $CodexRustDir "target" $targetDir "codex.exe"
    } else {
        Join-Path $CodexRustDir "target" $targetDir "codex"
    }

    if (-not (Test-Path $binary)) {
        Write-Error "Binary not found after build: $binary"
        exit 1
    }

    $binarySize = (Get-Item $binary).Length
    Write-Host "" -ForegroundColor Green
    Write-Host "✓ Build successful!" -ForegroundColor Green
    Write-Host "  Binary: $binary" -ForegroundColor Green
    Write-Host "  Size:   $([math]::Round($binarySize / 1MB, 1)) MB" -ForegroundColor Green
} finally {
    Pop-Location
}