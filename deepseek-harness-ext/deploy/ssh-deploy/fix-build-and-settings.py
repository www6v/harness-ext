"""
Fix build failure: ClientTransportHooks missing 'rpc' field.
Also fix "settings are unavailable in this browser" for remote access.
"""
import paramiko
import sys
import time
import socket

HOST = '111.229.26.170'
USER = 'root'
PASS = '1qaZxsw@'
DEPLOY_DIR = '/home/wei/deepseek-harness-ext/deploy'
SOURCE_DIR = '/home/wei/deepseek-harness'
LOCAL_DEPLOY_DIR = r'C:\mine\workspacePy\meta-harness\deepseek-harness-ext\deploy'
LOCAL_SOURCE_DIR = r'C:\mine\workspacePy\meta-harness\deepseek-harness'


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

# Upload modified source files
files_to_upload = [
    (r'packages\bundle\web-app\src\index.ts',
     f'{SOURCE_DIR}/packages/bundle/web-app/src/index.ts'),
    (r'packages\client\connection\src\client\index.ts',
     f'{SOURCE_DIR}/packages/client/connection/src/client/index.ts'),
]

for local_rel, remote_path in files_to_upload:
    local_path = f'{LOCAL_SOURCE_DIR}\\{local_rel}'
    print(f'Uploading {local_rel}...')
    sftp.put(local_path, remote_path)

sftp.close()
print('Source files uploaded!')

# Verify changes
cmd = f'grep "__DSH_TRUSTED_REMOTE__" {SOURCE_DIR}/packages/bundle/web-app/src/index.ts | head -2'
stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
print(f'Server injection: {stdout.read().decode().strip()}')

cmd = f'grep "rpc?:" {SOURCE_DIR}/packages/client/connection/src/client/index.ts'
stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
print(f'Client rpc field: {stdout.read().decode().strip()}')

cmd = f'grep "transport?.rpc" {SOURCE_DIR}/packages/client/connection/src/client/index.ts'
stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
print(f'Client rpc usage: {stdout.read().decode().strip()}')

# Copy Dockerfile and rebuild
cmd = f'cp {DEPLOY_DIR}/Dockerfile.optimized {DEPLOY_DIR}/Dockerfile'
stdin, stdout, stderr = client.exec_command(cmd, timeout=10)

print('\nStopping container...')
cmd = f'cd {DEPLOY_DIR} && docker compose down 2>&1'
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
    if any(k in stripped for k in ['DONE', 'ERROR', 'CACHED', 'exporting', 'naming', 'unpacking', 'Step']):
        print(stripped)
        sys.stdout.flush()

exit_code = stdout.channel.recv_exit_status()
print(f'\nBuild exit code: {exit_code}')

if exit_code != 0:
    print('BUILD FAILED')
    client.close()
    sys.exit(1)

print('\nStarting container...')
cmd = f'cd {DEPLOY_DIR} && docker compose up -d dsh 2>&1'
stdin, stdout, stderr = client.exec_command(cmd, timeout=60)
print(stdout.read().decode().strip())

print('\nWaiting 25s for startup...')
time.sleep(25)

cmd = f'cd {DEPLOY_DIR} && docker compose ps 2>&1'
stdin, stdout, stderr = client.exec_command(cmd, timeout=30)
print(f'\n=== Container Status ===\n{stdout.read().decode()}')

cmd = f'cd {DEPLOY_DIR} && docker compose logs dsh --tail=10 2>&1'
stdin, stdout, stderr = client.exec_command(cmd, timeout=30)
print(f'=== Logs ===\n{stdout.read().decode()}')

# Verify HTML injection
cmd = 'curl -sf http://127.0.0.1:3080/ -H "Host: 111.229.26.170:3080" | grep -o "__DSH_TRUSTED_REMOTE__" || echo "NOT FOUND"'
stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
print(f'HTML injection: {stdout.read().decode().strip()}')

# Get access URL
cmd = f'cd {DEPLOY_DIR} && docker compose logs dsh 2>&1 | grep -oP "token=[A-Za-z0-9_-]+" | head -1'
stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
token_line = stdout.read().decode().strip()

if token_line:
    print(f'\n Access: http://111.229.26.170:3080/?{token_line}')
    print('   Open this URL and check Settings — should work without errors')

client.close()
print('\nDone!')
