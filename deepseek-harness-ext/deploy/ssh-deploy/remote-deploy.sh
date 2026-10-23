#!/bin/bash
# =============================================================================
# DeepSeek Harness Remote Deployment Script
# Run this directly on the remote server
# =============================================================================

set -e

DEPLOY_DIR="/home/wei/deepseek-harness-ext/deploy"
BUILD_LOG="/tmp/dsh-build.log"

echo ""
echo "=============================================="
echo "DeepSeek Harness Deployment"
echo "=============================================="
echo ""

cd "$DEPLOY_DIR"

# Clean up previous build
echo "[0/7] Cleaning up previous build..."
docker compose down 2>/dev/null || true
rm -f /tmp/dsh-build.log 2>/dev/null || true

echo "[1/7] Setting up optimized Dockerfile..."
cp Dockerfile.optimized Dockerfile

echo "[2/7] Pulling base image..."
docker pull node:22-alpine || true

echo "[3/7] Clearing Docker build cache..."
docker builder prune -af 2>/dev/null || true

echo "[4/7] Starting background build..."
export DOCKER_BUILDKIT=1
export COMPOSE_DOCKER_CLI_BUILD=1

nohup docker compose build --progress=plain > "$BUILD_LOG" 2>&1 &
BUILD_PID=$!

echo "Build started with PID: $BUILD_PID"
echo "Build log: $BUILD_LOG"
echo ""

# Wait for build to complete
echo "[5/7] Monitoring build progress..."
WAIT_TIME=0
MAX_TIME=3600  # 60 minutes

while kill -0 $BUILD_PID 2>/dev/null; do
    sleep 60
    WAIT_TIME=$((WAIT_TIME + 60))

    MINUTES=$((WAIT_TIME / 60))

    # Show progress every minute
    echo "[$MINUTES min] Build in progress..."
    tail -5 "$BUILD_LOG" 2>/dev/null || true

    # Timeout check
    if [ $WAIT_TIME -ge $MAX_TIME ]; then
        echo "Timeout after $((MAX_TIME/60)) minutes"
        break
    fi
done

echo ""
echo "[6/7] Build complete! Final log entries:"
tail -50 "$BUILD_LOG"

# Check if build succeeded
if grep -q "ERROR" "$BUILD_LOG"; then
    echo ""
    echo "=============================================="
    echo "Build FAILED! Check the log for details."
    echo "=============================================="
    echo ""
    echo "Build log: $BUILD_LOG"
    exit 1
fi

echo ""
echo "[7/7] Starting containers..."
docker compose up -d

sleep 5

echo ""
echo "=============================================="
echo "Container Status"
echo "=============================================="
docker compose ps

echo ""
echo "=============================================="
echo "Recent Logs"
echo "=============================================="
docker compose logs --tail=20

echo ""
echo "=============================================="
echo "Deployment Complete!"
echo "=============================================="
echo ""
echo "Build log: $BUILD_LOG"
echo "View logs: docker compose logs -f"
echo ""
