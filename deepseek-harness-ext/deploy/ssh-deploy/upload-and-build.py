import paramiko
import sys
import time
import socket

HOST = '111.229.26.170'
USER = 'root'
PASS = '1qaZxsw@'
DEPLOY_DIR = '/home/wei/deepseek-harness-ext/deploy'
LOCAL_FILE = r'C:\mine\workspacePy\meta-harness\deepseek-harness-ext\deploy\Dockerfile.optimized'

def connect_with_retry(max_retries=5, retry_delay=30):
    """Connect with retries, waiting between attempts."""
    for attempt in range(max_retries):
        try:
            print(f'Attempt {attempt+1}/{max_retries}: Connecting to {HOST}...')
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            # Very generous timeouts
            client.connect(
                hostname=HOST,
                username=USER,
                password=PASS,
                timeout=300,
                banner_timeout=300,
                auth_timeout=60,
            )
            print('Connected!')
            return client
        except (paramiko.ssh_exception.SSHException, socket.timeout, OSError) as e:
            print(f'Failed: {e}')
            try:
                client.close()
            except:
                pass
            if attempt < max_retries - 1:
                print(f'Waiting {retry_delay}s before retry...')
                time.sleep(retry_delay)
            else:
                raise
    return None

client = connect_with_retry()

# Upload Dockerfile.optimized via SFTP
sftp = client.open_sftp()
print(f'Uploading to {DEPLOY_DIR}/Dockerfile.optimized...')
sftp.put(LOCAL_FILE, f'{DEPLOY_DIR}/Dockerfile.optimized')
sftp.close()
print('Upload complete!')

# Verify the uploaded file uses bookworm-slim
cmd = f'head -15 {DEPLOY_DIR}/Dockerfile.optimized'
stdin, stdout, stderr = client.exec_command(cmd, timeout=30)
content = stdout.read().decode('utf-8')
print(content)

if 'bookworm-slim' not in content:
    print('ERROR: Uploaded file does not contain bookworm-slim!')
    client.close()
    sys.exit(1)

print('Dockerfile verified - uses bookworm-slim')

# Check if server is under heavy load first
cmd = 'uptime && free -h && df -h / && docker ps -a --format "{{.Names}} {{.Status}}" 2>/dev/null | head -10'
stdin, stdout, stderr = client.exec_command(cmd, timeout=30)
print('\n=== Server Status ===')
print(stdout.read().decode('utf-8'))

# Kill any zombie containers and free resources
print('Cleaning up old containers...')
cmd = 'docker rm -f $(docker ps -aq --filter "name=deepseek") 2>/dev/null; docker system prune -f 2>/dev/null; echo "cleanup done"'
stdin, stdout, stderr = client.exec_command(cmd, timeout=60)
print(stdout.read().decode('utf-8'))

# Stop any running containers
print('\nStopping containers...')
cmd = f'cd {DEPLOY_DIR} && cp Dockerfile.optimized Dockerfile && docker compose down 2>/dev/null; echo "done"'
stdin, stdout, stderr = client.exec_command(cmd, timeout=60)
print(stdout.read().decode('utf-8'))

# Build with --no-cache
print('Building (this may take several minutes)...')
cmd = f'cd {DEPLOY_DIR} && docker compose --progress plain build --no-cache dsh 2>&1'
stdin, stdout, stderr = client.exec_command(cmd, timeout=1800)
while True:
    line = stdout.readline()
    if not line:
        break
    print(line, end='')
    sys.stdout.flush()

exit_code = stdout.channel.recv_exit_status()
print(f'\nBuild exit code: {exit_code}')

if exit_code != 0:
    print('BUILD FAILED')
    client.close()
    sys.exit(1)

# Start containers
print('\nStarting containers...')
cmd = f'cd {DEPLOY_DIR} && docker compose up -d dsh 2>&1'
stdin, stdout, stderr = client.exec_command(cmd, timeout=60)
print(stdout.read().decode('utf-8'))

# Wait and check status
time.sleep(15)
cmd = f'cd {DEPLOY_DIR} && docker compose ps 2>&1'
stdin, stdout, stderr = client.exec_command(cmd, timeout=30)
print(stdout.read().decode('utf-8'))

# Check logs
cmd = f'cd {DEPLOY_DIR} && docker compose logs dsh --tail=30 2>&1'
stdin, stdout, stderr = client.exec_command(cmd, timeout=30)
print(stdout.read().decode('utf-8'))

client.close()
print('Done!')
