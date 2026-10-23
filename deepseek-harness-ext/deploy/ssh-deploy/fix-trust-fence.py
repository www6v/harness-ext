"""
Fix HTTP 403 on /api/* endpoints.

Root cause: Docker container's trustedHosts only has internal IPs (172.x.x.x)
from networkInterfaces(), not the public IP 111.229.26.170. Browser requests
with Host: 111.229.26.170:3080 fail the trust fence → 403 Forbidden.

Fix: Add `command` override to docker-compose.yml with --trusted-host flag.
No image rebuild needed — just recreate the container.
"""
import paramiko
import time
import socket

HOST = '111.229.26.170'
USER = 'root'
PASS = '1qaZxsw@'
DEPLOY_DIR = '/home/wei/deepseek-harness-ext/deploy'
LOCAL_DEPLOY_DIR = r'C:\mine\workspacePy\meta-harness\deepseek-harness-ext\deploy'


def connect_with_retry(max_retries=3, retry_delay=15):
    for attempt in range(max_retries):
        try:
            print(f'Attempt {attempt+1}/{max_retries}: Connecting...')
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(hostname=HOST, username=USER, password=PASS,
                           timeout=120, banner_timeout=120)
            print('Connected!')
            return client
        except (paramiko.ssh_exception.SSHException, socket.timeout, OSError) as e:
            print(f'Failed: {e}')
            try:
                client.close()
            except:
                pass
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
            else:
                raise


client = connect_with_retry()
sftp = client.open_sftp()

# Upload updated docker-compose.yml (has command override with --trusted-host)
print('Uploading docker-compose.yml...')
sftp.put(f'{LOCAL_DEPLOY_DIR}\\docker-compose.yml', f'{DEPLOY_DIR}/docker-compose.yml')

# Also upload Dockerfile for future rebuilds
print('Uploading Dockerfile.optimized...')
sftp.put(f'{LOCAL_DEPLOY_DIR}\\Dockerfile.optimized', f'{DEPLOY_DIR}/Dockerfile.optimized')
sftp.close()
print('Upload complete!')

# Verify the command override is in the compose file
cmd = f'grep -A1 "command:" {DEPLOY_DIR}/docker-compose.yml | head -3'
stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
print(f'Compose command override:\n{stdout.read().decode().strip()}')

# Stop old container
print('\nStopping container...')
cmd = f'cd {DEPLOY_DIR} && docker compose down 2>&1'
stdin, stdout, stderr = client.exec_command(cmd, timeout=60)
print(stdout.read().decode().strip())

# Start with new command override (no rebuild needed)
print('\nStarting container with --trusted-host fix...')
cmd = f'cd {DEPLOY_DIR} && docker compose up -d dsh 2>&1'
stdin, stdout, stderr = client.exec_command(cmd, timeout=60)
print(stdout.read().decode().strip())

print('\nWaiting 25s for server startup...')
time.sleep(25)

# Check container status
cmd = f'cd {DEPLOY_DIR} && docker compose ps 2>&1'
stdin, stdout, stderr = client.exec_command(cmd, timeout=30)
print(f'\n=== Container Status ===\n{stdout.read().decode()}')

# Check logs for startup
cmd = f'cd {DEPLOY_DIR} && docker compose logs dsh --tail=15 2>&1'
stdin, stdout, stderr = client.exec_command(cmd, timeout=30)
logs = stdout.read().decode()
print(f'=== Logs (tail 15) ===\n{logs}')

# HTTP check on localhost
cmd = 'curl -sf -o /dev/null -w "%{http_code}" http://127.0.0.1:3080/'
stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
print(f'HTTP :3080 (localhost) => {stdout.read().decode().strip()}')

# Check that --trusted-host is in the running process cmdline
cmd = 'docker exec deepseek-harness cat /proc/1/cmdline 2>/dev/null | tr "\\0" " "'
stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
proc_cmdline = stdout.read().decode().strip()
print(f'\nContainer CMD: {proc_cmdline}')

# Test API endpoint with public IP host header (simulating browser request)
cmd = 'curl -sf -o /dev/null -w "%{http_code}" -H "Host: 111.229.26.170:3080" http://127.0.0.1:3080/api/llm/listProviders -X POST -H "Content-Type: application/json" -d \'{"rpcId":"test","method":"llm/listProviders","payload":{"args":{}}}\' 2>&1 || echo "FAILED"'
stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
api_result = stdout.read().decode().strip()
print(f'API test (Host: 111.229.26.170:3080) => {api_result}')

# Get access URL
cmd = f'cd {DEPLOY_DIR} && docker compose logs dsh 2>&1 | grep -oP "token=[A-Za-z0-9_-]+" | head -1'
stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
token_line = stdout.read().decode().strip()

if token_line:
    print(f'\n🌐 Access: http://111.229.26.170:3080/?{token_line}')
    print('   Open this URL in browser and verify API calls work (no more 403 errors)')

client.close()
print('\nDone!')
