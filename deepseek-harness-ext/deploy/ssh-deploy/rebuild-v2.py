import paramiko
import sys
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
            client.connect(hostname=HOST, username=USER, password=PASS, timeout=120, banner_timeout=120)
            print('Connected!')
            return client
        except (paramiko.ssh_exception.SSHException, socket.timeout, OSError) as e:
            print(f'Failed: {e}')
            try: client.close()
            except: pass
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
            else:
                raise

client = connect_with_retry()
sftp = client.open_sftp()

# Upload deploy files
for fname in ['Dockerfile.optimized', 'docker-compose.yml']:
    local = f'{LOCAL_DEPLOY_DIR}\\{fname}'
    remote = f'{DEPLOY_DIR}/{fname}'
    print(f'Uploading {fname}...')
    sftp.put(local, remote)

# Upload the modified startup.ts to the remote build context
local_startup = r'C:\mine\workspacePy\meta-harness\deepseek-harness\packages\bundle\web-app\src\startup.ts'
remote_startup = '/home/wei/deepseek-harness/packages/bundle/web-app/src/startup.ts'
print(f'Uploading startup.ts (source fix)...')
sftp.put(local_startup, remote_startup)
sftp.close()
print('Upload complete!')

# Verify CMD and key changes
cmd = f'grep "CMD" {DEPLOY_DIR}/Dockerfile.optimized | tail -1'
stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
print(f'CMD: {stdout.read().decode().strip()}')

# Verify startup.ts has DSH_ALLOW_WILDCARD_HOST change
# (this is in the build context which is the deepseek-harness source)

# Stop and rebuild
print('\nStopping containers...')
cmd = f'cd {DEPLOY_DIR} && cp Dockerfile.optimized Dockerfile && docker compose down 2>/dev/null; echo done'
stdin, stdout, stderr = client.exec_command(cmd, timeout=60)
print(stdout.read().decode().strip())

print('\nBuilding...')
cmd = f'cd {DEPLOY_DIR} && docker compose --progress plain build --no-cache dsh 2>&1'
stdin, stdout, stderr = client.exec_command(cmd, timeout=1800)

# Track key events
last_progress = ''
while True:
    line = stdout.readline()
    if not line:
        break
    # Print important lines, summarize progress
    if any(k in line for k in ['DONE', 'ERROR', 'CACHED', 'exporting', 'naming', 'unpacking', 'Build exit', '#13 $', '#13 ✔', 'web-app', 'startup']):
        stripped = line.strip()
        if stripped != last_progress:
            print(stripped)
            last_progress = stripped
            sys.stdout.flush()

exit_code = stdout.channel.recv_exit_status()
print(f'\nBuild exit code: {exit_code}')

if exit_code != 0:
    print('BUILD FAILED')
    client.close()
    sys.exit(1)

# Start
print('\nStarting containers...')
cmd = f'cd {DEPLOY_DIR} && docker compose up -d dsh 2>&1'
stdin, stdout, stderr = client.exec_command(cmd, timeout=60)
print(stdout.read().decode().strip())

# Wait for startup
time.sleep(20)

# Check status
cmd = f'cd {DEPLOY_DIR} && docker compose ps 2>&1'
stdin, stdout, stderr = client.exec_command(cmd, timeout=30)
print(f'\n=== Container Status ===\n{stdout.read().decode()}')

cmd = f'cd {DEPLOY_DIR} && docker compose logs dsh --tail=30 2>&1'
stdin, stdout, stderr = client.exec_command(cmd, timeout=30)
print(f'=== Logs (tail 30) ===\n{stdout.read().decode()}')

# HTTP health check
cmd = 'curl -sf -o /dev/null -w "%{http_code}" http://127.0.0.1:3000/ 2>&1 || echo "no-response"'
stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
status = stdout.read().decode().strip()
print(f'=== HTTP Status on :3000 === {status}')

# Also try port 3080 as fallback
cmd = 'curl -sf -o /dev/null -w "%{http_code}" http://127.0.0.1:3080/ 2>&1 || echo "no-response"'
stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
status2 = stdout.read().decode().strip()
print(f'=== HTTP Status on :3080 === {status2}')

client.close()
print('Done!')
