#!/bin/bash
# Setup script for Codex PoC deployment on Ubuntu 24.04
# Run as root on 124.221.28.203
set -euo pipefail

echo "=== [1/4] Installing Rust via rustup (TUNA mirror) ==="
if command -v rustc &>/dev/null; then
    echo "Rust already installed: $(rustc --version)"
else
    export RUSTUP_DIST_SERVER="https://mirrors.tuna.tsinghua.edu.cn/rustup"
    export RUSTUP_UPDATE_ROOT="https://mirrors.tuna.tsinghua.edu.cn/rustup/rustup"
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --default-toolchain stable
    source "$HOME/.cargo/env"
    echo "Rust installed: $(rustc --version)"
fi

echo ""
echo "=== [2/4] Configuring Cargo (TUNA mirror) ==="
mkdir -p ~/.cargo
cat > ~/.cargo/config.toml << 'EOF'
[source.crates-io]
replace-with = 'tuna'

[source.tuna]
registry = "sparse+https://mirrors.tuna.tsinghua.edu.cn/crates.io-index/"

[target.x86_64-unknown-linux-gnu]
# Limit parallel jobs to avoid OOM on 3.6GB RAM
rustflags = ["-C", "link-arg=-Wl,--as-needed"]
EOF

# Set build jobs limit via env
grep -q "CARGO_BUILD_JOBS" ~/.bashrc || echo 'export CARGO_BUILD_JOBS=1' >> ~/.bashrc
grep -q "CARGO_NET_RETRY" ~/.bashrc || echo 'export CARGO_NET_RETRY=3' >> ~/.bashrc
export CARGO_BUILD_JOBS=1
echo "Cargo configured with TUNA mirror + job limit"

echo ""
echo "=== [3/4] Moving Docker data to /data/disk ==="
CURRENT_ROOT=$(docker info --format '{{.DockerRootDir}}' 2>/dev/null || echo "/var/lib/docker")
if [ "$CURRENT_ROOT" = "/data/disk/docker" ]; then
    echo "Docker already uses /data/disk/docker"
else
    echo "Stopping Docker..."
    systemctl stop docker docker.socket 2>/dev/null || true

    if [ -d /data/disk/docker ] && [ "$(ls -A /data/disk/docker 2>/dev/null)" ]; then
        echo "/data/disk/docker already has data, backing up current..."
    fi

    # Create daemon config
    mkdir -p /etc/docker
    if [ -f /etc/docker/daemon.json ]; then
        # Merge with existing config
        python3 -c "
import json
try:
    with open('/etc/docker/daemon.json') as f:
        cfg = json.load(f)
except:
    cfg = {}
cfg['data-root'] = '/data/disk/docker'
with open('/etc/docker/daemon.json', 'w') as f:
    json.dump(cfg, f, indent=2)
print('daemon.json updated:', json.dumps(cfg, indent=2))
"
    else
        echo '{"data-root": "/data/disk/docker"}' > /etc/docker/daemon.json
    fi

    echo "Starting Docker..."
    systemctl start docker
    sleep 2
    echo "Docker data root: $(docker info --format '{{.DockerRootDir}}')"
fi

echo ""
echo "=== [4/4] Create workspace on /data/disk ==="
mkdir -p /data/disk/codex-build
mkdir -p /data/disk/codex-deploy
echo "Workspace ready: /data/disk/codex-build, /data/disk/codex-deploy"

echo ""
echo "=== Setup complete ==="
source "$HOME/.cargo/env"
rustc --version
cargo --version
docker --version
df -h /data/disk | tail -1