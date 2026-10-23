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

for fname in ['Dockerfile.optimized', 'docker-compose.yml']:
    local = f'{LOCAL_DEPLOY_DIR}\\{fname}'
    remote = f'{DEPLOY_DIR}/{fname}'
    print(f'Uploading {fname}...')
    sftp.put(local, remote)
sftp.close()
print('Upload complete!')

# Verify ports changed
cmd = f'grep -E "EXPOSE|CMD|port" {DEPLOY_DIR}/Dockerfile.optimized | grep 30'
stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
print(f'Dockerfile ports:\n{stdout.read().decode().strip()}')

# Stop and rebuild (CMD changed so image rebuild is needed)
print('\nStopping containers...')
cmd = f'cd {DEPLOY_DIR} && cp Dockerfile.optimized Dockerfile && docker compose down 2>/dev/null; echo done'
stdin, stdout, stderr = client.exec_command(cmd, timeout=60)
print(stdout.read().decode().strip())

print('\nBuilding...')
cmd = f'cd {DEPLOY_DIR} && docker compose --progress plain build --no-cache dsh 2>&1'
stdin, stdout, stderr = client.exec_command(cmd, timeout=1800)
while True:
    line = stdout.readline()
    if not line:
        break
    stripped = line.strip()
    if any(k in stripped for k in ['DONE', 'ERROR', 'CACHED', 'exporting', 'naming', 'unpacking']):
        print(stripped)
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

time.sleep(20)

cmd = f'cd {DEPLOY_DIR} && docker compose ps 2>&1'
stdin, stdout, stderr = client.exec_command(cmd, timeout=30)
print(f'\n=== Container Status ===\n{stdout.read().decode()}')

cmd = f'cd {DEPLOY_DIR} && docker compose logs dsh --tail=10 2>&1'
stdin, stdout, stderr = client.exec_command(cmd, timeout=30)
print(f'=== Logs (tail 10) ===\n{stdout.read().decode()}')

# HTTP check on 3080
cmd = 'curl -sf -o /dev/null -w "%{http_code}" http://127.0.0.1:3080/ 2>&1 || echo "no-response"'
stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
print(f'HTTP :3080 => {stdout.read().decode().strip()}')

# Get token for access URL
cmd = f'cd {DEPLOY_DIR} && docker compose logs dsh 2>&1 | grep -oP "token=[A-Za-z0-9_-]+" | head -1'
stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
token_line = stdout.read().decode().strip()
if token_line:
    print(f'\n🌐 Access: http://111.229.26.170:3080/?{token_line}')

client.close()
print('Done!')
