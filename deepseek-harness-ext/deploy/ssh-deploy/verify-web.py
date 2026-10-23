import paramiko

HOST = '111.229.26.170'
USER = 'root'
PASS = '1qaZxsw@'
DEPLOY_DIR = '/home/wei/deepseek-harness-ext/deploy'

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(hostname=HOST, username=USER, password=PASS, timeout=60, banner_timeout=60)

# Get token
cmd = f'cd {DEPLOY_DIR} && docker compose logs dsh 2>&1 | grep -oP "token=[A-Za-z0-9_-]+" | head -1'
stdin, stdout, stderr = client.exec_command(cmd, timeout=30)
token = stdout.read().decode().strip().replace('token=', '')
print(f'Token: {token}')

# Follow redirects and check final page
cmd = f'curl -sL -w "\\n---HTTP_CODE:%{{http_code}}---" "http://127.0.0.1:3000/?token={token}" | tail -20'
stdin, stdout, stderr = client.exec_command(cmd, timeout=15)
resp = stdout.read().decode().strip()
print(f'\n=== Response (with redirect follow) ===')
print(resp[:1000])

# Also check the health endpoint
cmd = f'cd {DEPLOY_DIR} && docker compose ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" 2>&1'
stdin, stdout, stderr = client.exec_command(cmd, timeout=15)
print(f'\n=== Container Status ===\n{stdout.read().decode()}')

# Show full URL for browser access
print(f'\n🌐 Access URL: http://111.229.26.170:3000/?token={token}')

client.close()
