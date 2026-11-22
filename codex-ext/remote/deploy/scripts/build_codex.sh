#!/bin/bash
# Build codex binary from patched source on /data/disk
set -euo pipefail

source "$HOME/.cargo/env"
export CARGO_BUILD_JOBS=1
export CARGO_NET_RETRY=3

cd /data/disk/codex-build/codex-rs

echo "=== Building codex (this will take 15-25 min) ==="
echo "Rust: $(rustc --version)"
echo "Cargo: $(cargo --version)"
echo "Build jobs: $CARGO_BUILD_JOBS"
echo "Start: $(date)"
echo ""

# Build codex binary (debug for faster build, release for performance)
cargo build --bin codex --release 2>&1

echo ""
echo "=== Build complete ==="
echo "End: $(date)"

# Check binary
BIN="target/release/codex"
if [ -f "$BIN" ]; then
    echo "Binary: $BIN"
    ls -lh "$BIN"
    echo "Version: $($BIN --version 2>&1 || true)"
else
    echo "ERROR: Binary not found!"
    exit 1
fi