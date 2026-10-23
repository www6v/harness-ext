#!/usr/bin/env python3
"""Deploy DeepSeek Harness to 124.221.28.203"""
import paramiko
import sys
import time

HOST = '124.221.28.203'
USER = 'root'
PASS = '1qaZxsw@'
EXT_DIR = '/home/ubuntu/wei/deepseek-harness-ext/deploy'
SRC_DIR = '/home/ubuntu/wei/deepseek-harness'

def run(client, cmd, timeout=30, show=True):
    """Run command, print output, return (exit_code, stdout_text)"""
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    code = stdout.channel.recv_exit_status()
    if show:
        if out: print(out)
        if err: print(f'[stderr] {err}')
    return code, out

def run_streaming(client, cmd, timeout=1800):
    """Run command with streaming output for long builds"""
    print(f'\n>>> {cmd[:120]}...' if len(cmd) > 120 else f'\n>>> {cmd}')
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    errors = []
    for line in iter(stdout.readline, ''):
        s = line.rstrip()
        if s:
            print(s)
            sys.stdout.flush()
        if 'error TS' in s or 'ERROR' in s:
            errors.append(s)
    exit_code = stdout.channel.recv_exit_status()
    return exit_code, errors

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
print(f'Connecting to {HOST}...')
client.connect(hostname=HOST, username=USER, password=PASS, timeout=30, banner_timeout=30)
print('Connected!\n')

# ===== Step 0: Check current state =====
print('='*60)
print('Step 0: Check current state')
print('='*60)
run(client, f'ls -la {EXT_DIR}/docker-compose.yml {EXT_DIR}/Dockerfile.optimized 2>&1')
run(client, f'cat {EXT_DIR}/docker-compose.yml | grep trusted-host || echo "no trusted-host found"')
run(client, 'docker ps -a --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" 2>&1 | head -10')

# ===== Step 1: Configure Docker registry mirror =====
print('\n' + '='*60)
print('Step 1: Configure Docker registry mirror (China)')
print('='*60)

# Check if already configured
code, out = run(client, 'cat /etc/docker/daemon.json 2>/dev/null || echo "{}"')
if 'registry-mirrors' not in out:
    print('Configuring Docker registry mirrors...')
    daemon_json = '''{
  "registry-mirrors": [
    "https://docker.1ms.run",
    "https://docker.xuanyuan.me",
    "https://docker.m.daocloud.io"
  ]
}'''
    run(client, f"echo '{daemon_json}' > /etc/docker/daemon.json")
    run(client, 'systemctl daemon-reload')
    run(client, 'systemctl restart docker')
    time.sleep(3)
    run(client, 'docker info 2>/dev/null | grep -A5 "Registry Mirrors"')
    print('Docker mirrors configured!')
else:
    print('Docker mirrors already configured.')

# ===== Step 2: Clean up disk space =====
print('\n' + '='*60)
print('Step 2: Clean up disk space')
print('='*60)
run(client, 'df -h / | tail -1')
# Clean old docker images
run(client, 'docker image prune -f 2>&1 | tail -3')
run(client, 'docker builder prune -f 2>&1 | tail -3')
run(client, 'df -h / | tail -1')

# ===== Step 3: Update trusted-host for new IP =====
print('\n' + '='*60)
print('Step 3: Update trusted-host to 124.221.28.203')
print('='*60)
# Use sed to replace the old IP with the new one in docker-compose.yml
run(client, f"sed -i 's/111.229.26.170/124.221.28.203/g' {EXT_DIR}/docker-compose.yml")
run(client, f"grep trusted-host {EXT_DIR}/docker-compose.yml")
# Also update Dockerfile.optimized CMD
run(client, f"sed -i 's/111.229.26.170/124.221.28.203/g' {EXT_DIR}/Dockerfile.optimized")
run(client, f"grep trusted-host {EXT_DIR}/Dockerfile.optimized")

# ===== Step 4: Copy Dockerfile.optimized to Dockerfile =====
print('\n' + '='*60)
print('Step 4: Prepare Dockerfile')
print('='*60)
run(client, f'cp {EXT_DIR}/Dockerfile.optimized {EXT_DIR}/Dockerfile')

# ===== Step 5: Stop any existing containers =====
print('\n' + '='*60)
print('Step 5: Stop existing containers')
print('='*60)
run(client, f'cd {EXT_DIR} && docker compose down 2>&1')

# ===== Step 6: Build =====
print('\n' + '='*60)
print('Step 6: Build Docker image (China optimized)')
print('='*60)
build_cmd = f'cd {EXT_DIR} && DOCKER_BUILDKIT=1 COMPOSE_DOCKER_CLI_BUILD=1 docker compose --progress plain build --no-cache dsh 2>&1'
exit_code, errors = run_streaming(client, build_cmd, timeout=1800)
print(f'\nBuild exit code: {exit_code}')
if errors:
    print(f'Errors ({len(errors)}):')
    for e in errors[:10]:
        print(f'  {e}')

if exit_code != 0:
    print('BUILD FAILED!')
    client.close()
    sys.exit(1)

# ===== Step 7: Start =====
print('\n' + '='*60)
print('Step 7: Start containers')
print('='*60)
run(client, f'cd {EXT_DIR} && docker compose up -d dsh 2>&1')

# Wait for health check
print('Waiting for container to become healthy...')
for i in range(12):
    time.sleep(10)
    code, out = run(client, f'cd {EXT_DIR} && docker compose ps 2>&1', show=False)
    if 'healthy' in out:
        print(f'Container healthy after {(i+1)*10}s!')
        break
    print(f'  {(i+1)*10}s: waiting...')
    # Show current status
    run(client, f'cd {EXT_DIR} && docker compose ps --format "table {{{{.Name}}}}\t{{{{.Status}}}}" 2>&1', show=True)

# ===== Step 8: Final verification =====
print('\n' + '='*60)
print('Step 8: Final verification')
print('='*60)
run(client, f'cd {EXT_DIR} && docker compose ps 2>&1')
run(client, f'cd {EXT_DIR} && docker compose logs dsh --tail=5 2>&1')
# Get access token
code, token_line = run(client, f'cd {EXT_DIR} && docker compose logs dsh 2>&1 | grep -oP "token=[A-Za-z0-9_-]+" | head -1', show=False)
if token_line:
    print(f'\nAccess URL: http://124.221.28.203:3080/?{token_line}')

# Test API
print('\nAPI test:')
run(client, 'curl -sf -o /dev/null -w "HTTP %{http_code}" -H "Host: 124.221.28.203:3080" http://127.0.0.1:3080/ 2>&1 || echo "FAILED"')

client.close()
print('\n' + '='*60)
print('Deployment complete!')
print('='*60)
