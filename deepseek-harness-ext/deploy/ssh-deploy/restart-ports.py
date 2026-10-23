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

# Upload updated docker-compose.yml
local = f'{LOCAL_DEPLOY_DIR}\\docker-compose.yml'
remote = f'{DEPLOY_DIR}/docker-compose.yml'
print(f'Uploading docker-compose.yml...')
sftp.put(local, remote)
sftp.close()
print('Upload complete!')

# Restart containers
print('\nRestarting containers...')
cmd = f'cd {DEPLOY_DIR} && docker compose down 2>/dev/null && docker compose up -d dsh 2>&1'
stdin, stdout, stderr = client.exec_command(cmd, timeout=60)
print(stdout.read().decode().strip())

# Wait for web server startup
print('\nWaiting 20s for startup...')
time.sleep(20)

# Check status
cmd = f'cd {DEPLOY_DIR} && docker compose ps 2>&1'
stdin, stdout, stderr = client.exec_command(cmd, timeout=30)
print(f'\n=== Container Status ===\n{stdout.read().decode()}')

cmd = f'cd {DEPLOY_DIR} && docker compose logs dsh --tail=15 2>&1'
stdin, stdout, stderr = client.exec_command(cmd, timeout=30)
print(f'=== Logs (tail 15) ===\n{stdout.read().decode()}')

# HTTP health check
cmd = 'curl -sf -o /dev/null -w "%{http_code}" http://127.0.0.1:3000/ 2>&1 || echo "no-response"'
stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
status = stdout.read().decode().strip()
print(f'=== HTTP Status on :3000 === {status}')

# Check public IP accessibility
cmd = "curl -sf -o /dev/null -w '%{http_code}' --connect-timeout 5 http://111.229.26.170:3000/ 2>&1 || echo 'no-response'"
stdin, stdout, stderr = client.exec_command(cmd, timeout=15)
status2 = stdout.read().decode().strip()
print(f'=== HTTP Status via public IP :3000 === {status2}')

client.close()
print('\nDone!')
