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

# Check current docker-compose.yml ports config
cmd = f'grep -A2 "ports" {DEPLOY_DIR}/docker-compose.yml | head -10'
stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
print(f'Ports config:\n{stdout.read().decode()}')

# Check current container ports
cmd = f'docker inspect deepseek-harness --format "{{{{json .HostConfig.PortBindings}}}}" 2>/dev/null || echo "not found"'
stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
print(f'Container port bindings: {stdout.read().decode().strip()}')

# Force recreate container
print('\nForce recreating container...')
cmd = f'cd {DEPLOY_DIR} && docker compose down && docker compose up -d dsh 2>&1'
stdin, stdout, stderr = client.exec_command(cmd, timeout=60)
print(stdout.read().decode().strip())

time.sleep(20)

# Check status
cmd = f'cd {DEPLOY_DIR} && docker compose ps 2>&1'
stdin, stdout, stderr = client.exec_command(cmd, timeout=30)
print(f'\n=== Container Status ===\n{stdout.read().decode()}')

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
