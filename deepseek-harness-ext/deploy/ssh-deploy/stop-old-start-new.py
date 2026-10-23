import paramiko
import time

HOST = '111.229.26.170'
USER = 'root'
PASS = '1qaZxsw@'
DEPLOY_DIR = '/home/wei/deepseek-harness-ext/deploy'

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(hostname=HOST, username=USER, password=PASS, timeout=60, banner_timeout=60)
print('Connected!')

# Kill the old dsh process
print('Stopping old dsh instance (pid 958)...')
cmd = 'kill 958 && echo "killed" || echo "already dead"'
stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
print(stdout.read().decode().strip())

time.sleep(2)

# Verify port is free
cmd = 'ss -tlnp | grep 3080 || echo "port 3080 is free"'
stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
print(f'Port check: {stdout.read().decode().strip()}')

# Start Docker container
print('\nStarting Docker container...')
cmd = f'cd {DEPLOY_DIR} && docker compose up -d dsh 2>&1'
stdin, stdout, stderr = client.exec_command(cmd, timeout=60)
out = stdout.read().decode().strip()
print(out)

time.sleep(20)

# Check status
cmd = f'cd {DEPLOY_DIR} && docker compose ps 2>&1'
stdin, stdout, stderr = client.exec_command(cmd, timeout=30)
print(f'\n=== Container Status ===\n{stdout.read().decode()}')

cmd = f'cd {DEPLOY_DIR} && docker compose logs dsh --tail=10 2>&1'
stdin, stdout, stderr = client.exec_command(cmd, timeout=30)
logs = stdout.read().decode()
print(f'=== Logs (tail 10) ===\n{logs}')

# HTTP check
cmd = 'curl -sf -o /dev/null -w "%{http_code}" http://127.0.0.1:3080/'
stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
print(f'HTTP :3080 => {stdout.read().decode().strip()}')

# Get access URL
cmd = f'cd {DEPLOY_DIR} && docker compose logs dsh 2>&1 | grep -oP "token=[A-Za-z0-9_-]+" | head -1'
stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
token_line = stdout.read().decode().strip()
if token_line:
    print(f'\n🌐 Access: http://111.229.26.170:3080/?{token_line}')

client.close()
