#!/bin/bash
# Codex PoC — Docker Deploy Script
# Run on remote server: bash /home/wei/meta-harness/codex-ext/deploy/deploy.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BUILD_DIR="/data/disk/codex-build"
BINARY="${BUILD_DIR}/codex-rs/target/release/codex"
IMAGE="codex-server:poc"

echo "=== Codex PoC Deployment ==="
echo ""

# [1/5] Verify binary
if [ ! -f "$BINARY" ]; then
    echo "ERROR: Codex binary not found at $BINARY"
    echo "Build it first: bash /data/disk/build_codex.sh"
    exit 1
fi
echo "[1/5] Binary: $($BINARY --version 2>&1 || true)"
ls -lh "$BINARY"

# [2/5] Prepare build context (copy config next to binary)
echo "[2/5] Preparing build context..."
cp "$SCRIPT_DIR/config.toml" "$BUILD_DIR/config.toml"

# [3/5] Build Docker image
echo "[3/5] Building Docker image..."
cd "$BUILD_DIR"
docker build -t "$IMAGE" -f "$SCRIPT_DIR/Dockerfile" .

echo ""
echo "Image size:"
docker images "$IMAGE" --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}"

# [4/5] Stop and remove old container
echo ""
echo "[4/5] Stopping old container..."
docker stop codex-poc 2>/dev/null || true
docker rm codex-poc 2>/dev/null || true

# [5/5] Start new container
echo "[5/5] Starting codex-server..."
docker run -d \
    --name codex-poc \
    --restart unless-stopped \
    -p 8765:8765 \
    -e DASHSCOPE_API_KEY="${DASHSCOPE_API_KEY:-sk-e4586ec037624d6792b1c7a4a850cef2}" \
    "$IMAGE" \
    app-server --listen ws://0.0.0.0:8765 \
    --ws-auth capability-token \
    --ws-token-file /home/codex/.codex/ws-token

sleep 3

echo ""
echo "=== Container Status ==="
docker ps --filter name=codex-poc --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

echo ""
echo "=== Recent Logs ==="
docker logs --tail 20 codex-poc

echo ""
echo "=== Done ==="
echo "WebSocket: ws://$(hostname -I | awk '{print $1}'):8765"
echo "Logs:      docker logs -f codex-poc"