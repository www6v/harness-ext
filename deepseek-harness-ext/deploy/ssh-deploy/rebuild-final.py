import paramiko
import sys
import time
import socket

HOST = '111.229.26.170'
USER = 'root'
PASS = '1qaZxsw@'
DEPLOY_DIR = '/home/wei/deepseek-harness-ext/deploy'
SOURCE_DIR = '/home/wei/deepseek-harness'
LOCAL_SOURCE_DIR = r'C:\mine\workspacePy\meta-harness\deepseek-harness'

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
            if attempt < max_retries - 1: time.sleep(retry_delay)
            else: raise

client = connect_with_retry()
sftp = client.open_sftp()

print('Uploading fixed client/index.ts...')
sftp.put(f'{LOCAL_SOURCE_DIR}\\packages\\client\\connection\\src\\client\\index.ts',
         f'{SOURCE_DIR}/packages/client/connection/src/client/index.ts')
sftp.close()

# Verify fix
cmd = f'grep "fetch?:" {SOURCE_DIR}/packages/client/connection/src/client/index.ts'
stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
print(f'fetch optional: {stdout.read().decode().strip()}')

cmd = f'cp {DEPLOY_DIR}/Dockerfile.optimized {DEPLOY_DIR}/Dockerfile'
stdin, stdout, stderr = client.exec_command(cmd, timeout=10)

print('\nStopping...')
cmd = f'cd {DEPLOY_DIR} && docker compose down 2>&1'
stdin, stdout, stderr = client.exec_command(cmd, timeout=60)
print(stdout.read().decode().strip())

print('\nBuilding...')
cmd = f'cd {DEPLOY_DIR} && docker compose --progress plain build --no-cache dsh 2>&1'
stdin, stdout, stderr = client.exec_command(cmd, timeout=1800)
errors = []
for line in iter(stdout.readline, ''):
    s = line.strip()
    if 'error TS' in s or 'ERROR' in s:
        errors.append(s)
    if any(k in s for k in ['DONE', 'CACHED', 'exporting', 'Step']):
        print(s)
        sys.stdout.flush()

exit_code = stdout.channel.recv_exit_status()
print(f'\nBuild exit code: {exit_code}')
if errors:
    print(f'\nErrors ({len(errors)}):')
    for e in errors[:10]: print(e)

if exit_code != 0:
    print('BUILD FAILED')
    client.close()
    sys.exit(1)

print('\nStarting...')
cmd = f'cd {DEPLOY_DIR} && docker compose up -d dsh 2>&1'
stdin, stdout, stderr = client.exec_command(cmd, timeout=60)
print(stdout.read().decode().strip())

time.sleep(25)

cmd = f'cd {DEPLOY_DIR} && docker compose ps 2>&1'
stdin, stdout, stderr = client.exec_command(cmd, timeout=30)
print(f'\nStatus:\n{stdout.read().decode()}')

cmd = f'cd {DEPLOY_DIR} && docker compose logs dsh --tail=5 2>&1'
stdin, stdout, stderr = client.exec_command(cmd, timeout=30)
print(f'Logs:\n{stdout.read().decode()}')

cmd = 'curl -sf http://127.0.0.1:3080/ -H "Host: 111.229.26.170:3080" | grep -o "__DSH_TRUSTED_REMOTE__" || echo "NOT FOUND"'
stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
print(f'HTML injection: {stdout.read().decode().strip()}')

cmd = f'cd {DEPLOY_DIR} && docker compose logs dsh 2>&1 | grep -oP "token=[A-Za-z0-9_-]+" | head -1'
stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
token = stdout.read().decode().strip()
if token:
    print(f'\nAccess: http://111.229.26.170:3080/?{token}')

client.close()
print('\nDone!')
