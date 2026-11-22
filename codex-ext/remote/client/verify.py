"""Verify codex app-server is accessible and test remote SDK bridge."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ssh import get_remote_host

with get_remote_host() as h:
    # 1. Test readyz
    print("=== Test 1: readyz endpoint ===")
    r = h.run("curl -s http://localhost:8765/readyz 2>&1")
    print(f"readyz: {r.stdout.strip()}")

    # 2. Test healthz
    print("\n=== Test 2: healthz endpoint ===")
    r = h.run("curl -s http://localhost:8765/healthz 2>&1")
    print(f"healthz: {r.stdout.strip()}")

    # 3. Check if port is reachable from outside
    print("\n=== Test 3: Container status ===")
    r = h.run("docker ps --filter name=codex-poc --format '{{.ID}} {{.Status}} {{.Image}}'")
    print(f"Container: {r.stdout.strip()}")

    # 4. Check WebSocket connectivity
    print("\n=== Test 4: WebSocket test ===")
    r = h.run("python3 -c \"import websockets; print('websockets available')\" 2>&1 || echo 'websockets not installed'")
    print(r.stdout.strip())

    # 5. Docker logs
    print("\n=== Test 5: Container logs ===")
    r = h.run("docker logs codex-poc 2>&1 | head -20")
    print(r.stdout)