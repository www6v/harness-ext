"""Deploy codex Docker container on 124.221.28.203."""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ssh import get_remote_host

LOCAL_DEPLOY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "deploy")

with get_remote_host() as h:
    # 1. Upload Dockerfile and config.toml to build context
    print("=== Step 1: Upload deploy files ===")
    h.upload_file(
        os.path.join(LOCAL_DEPLOY, "Dockerfile"),
        "/data/disk/codex-build/Dockerfile"
    )
    h.upload_file(
        os.path.join(LOCAL_DEPLOY, "config.toml"),
        "/data/disk/codex-build/config.toml"
    )
    print("Files uploaded.")

    # 2. Verify binary exists
    print("\n=== Step 2: Verify binary ===")
    r = h.run("ls -lh /data/disk/codex-build/codex-rs/target/release/codex")
    print(r.stdout.strip())

    # 3. Remove old container if exists
    print("\n=== Step 3: Clean old container ===")
    h.run("docker stop codex-poc 2>/dev/null || true")
    h.run("docker rm codex-poc 2>/dev/null || true")
    print("Old container cleaned.")

    # 4. Build Docker image (use host network to bypass broken docker0 bridge)
    print("\n=== Step 4: Build Docker image ===")
    r = h.run("cd /data/disk/codex-build && docker build --network host -t codex-server:poc -f Dockerfile . 2>&1", timeout=300)
    print(r.stdout[-2000:] if len(r.stdout) > 2000 else r.stdout)

    # 5. Run container (use host network to bypass broken docker0 bridge)
    print("\n=== Step 5: Start container ===")
    h.run(
        "docker run -d --name codex-poc --restart unless-stopped "
        "--network host "
        "-e DASHSCOPE_API_KEY=sk-e4586ec037624d6792b1c7a4a850cef2 "
        "codex-server:poc "
        "app-server --listen ws://0.0.0.0:8765 "
        "--ws-auth capability-token "
        "--ws-token-file /home/codex/.codex/ws-token",
        timeout=30
    )
    time.sleep(3)

    # 6. Verify container
    print("\n=== Step 6: Verify container ===")
    r = h.run("docker ps --filter name=codex-poc --format '{{.ID}} {{.Status}} {{.Ports}}'")
    print(f"Container: {r.stdout.strip()}")

    r = h.run("docker logs codex-poc 2>&1 | tail -10")
    print(f"Logs:\n{r.stdout}")