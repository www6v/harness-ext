import paramiko
import sys
import time
import socket

HOST = '111.229.26.170'
USER = 'root'
PASS = '1qaZxsw@'
DEPLOY_DIR = '/home/wei/deepseek-harness-ext/deploy'
LOCAL_DIR = r'C:\mine\workspacePy\meta-harness\deepseek-harness-ext\deploy'

def connect_with_retry(max_retries=3, retry_delay=15):
    for attempt in range(max_retries):
        try:
            print(f'Attempt {attempt+1}/{max_retries}: Connecting to {HOST}...')
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
                print(f'Waiting {retry_delay}s...')
                time.sleep(retry_delay)
            else:
                raise

client = connect_with_retry()
sftp = client.open_sftp()

# Upload modified files
for fname in ['Dockerfile.optimized', 'docker-compose.yml']:
    local = f'{LOCAL_DIR}\\{fname}'
    remote = f'{DEPLOY_DIR}/{fname}'
    print(f'Uploading {fname}...')
    sftp.put(local, remote)
    print(f'  -> {remote}')
sftp.close()
print('Upload complete!')

# Verify key changes
cmd = f'grep "CMD" {DEPLOY_DIR}/Dockerfile.optimized'
stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
print(f'CMD in Dockerfile: {stdout.read().decode().strip()}')

# Copy Dockerfile and rebuild (only rebuild dsh service, should be fast since only CMD changed)
print('\nStopping containers...')
cmd = f'cd {DEPLOY_DIR} && cp Dockerfile.optimized Dockerfile && docker compose down 2>/dev/null; echo done'
stdin, stdout, stderr = client.exec_command(cmd, timeout=60)
print(stdout.read().decode().strip())

print('\nBuilding (should be fast - only CMD changed)...')
cmd = f'cd {DEPLOY_DIR} && docker compose --progress plain build --no-cache dsh 2>&1'
stdin, stdout, stderr = client.exec_command(cmd, timeout=600)
while True:
    line = stdout.readline()
    if not line:
        break
    # Only print key lines to avoid flooding
    if any(k in line for k in ['DONE', 'ERROR', 'CACHED', 'exporting', 'naming', 'unpacking', 'Build', 'exit']):
        print(line, end='')
        sys.stdout.flush()

exit_code = stdout.channel.recv_exit_status()
print(f'\nBuild exit code: {exit_code}')

if exit_code != 0:
    # Print last 30 lines on failure
    print('BUILD FAILED - dumping tail...')
    client.close()
    sys.exit(1)

# Start
print('\nStarting containers...')
cmd = f'cd {DEPLOY_DIR} && docker compose up -d dsh 2>&1'
stdin, stdout, stderr = client.exec_command(cmd, timeout=60)
print(stdout.read().decode().strip())

# Wait and check
time.sleep(15)

cmd = f'cd {DEPLOY_DIR} && docker compose ps 2>&1'
stdin, stdout, stderr = client.exec_command(cmd, timeout=30)
print(f'\n=== Container Status ===\n{stdout.read().decode()}')

cmd = f'cd {DEPLOY_DIR} && docker compose logs dsh --tail=30 2>&1'
stdin, stdout, stderr = client.exec_command(cmd, timeout=30)
print(f'=== Logs (tail 30) ===\n{stdout.read().decode()}')

# Health check
cmd = 'curl -sf -o /dev/null -w "%{http_code}" http://127.0.0.1:3000/ 2>&1 || echo "no-response"'
stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
status = stdout.read().decode().strip()
print(f'\n=== HTTP Status on :3000 === {status}')

client.close()
print('Done!')
