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

# Use cookie jar for auth flow
cmd = f'''rm -f /tmp/dsh-cookies && \
curl -sL -c /tmp/dsh-cookies -w "\\nHTTP_CODE:%{{http_code}}" \
  "http://127.0.0.1:3000/?token={token}" -o /tmp/dsh-page.html && \
echo "=== After auth ===" && \
curl -sL -b /tmp/dsh-cookies -w "\\nHTTP_CODE:%{{http_code}}" \
  "http://127.0.0.1:3000/" -o /tmp/dsh-page2.html && \
echo "=== Page size ===" && \
wc -c /tmp/dsh-page.html /tmp/dsh-page2.html && \
echo "=== Page 2 head ===" && \
head -5 /tmp/dsh-page2.html'''
stdin, stdout, stderr = client.exec_command(cmd, timeout=15)
print(stdout.read().decode().strip())

# Also check /health or /api/health
cmd = 'curl -sf "http://127.0.0.1:3000/health" -o /dev/null -w "%{http_code}" 2>&1 || echo "no-health-endpoint"'
stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
print(f'\n/health endpoint: {stdout.read().decode().strip()}')

# Check if /api works
cmd = 'curl -sf "http://127.0.0.1:3000/api/" -o /dev/null -w "%{http_code}" 2>&1 || echo "no-api"'
stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
print(f'/api/ endpoint: {stdout.read().decode().strip()}')

# Show full access info
cmd = f'cd {DEPLOY_DIR} && docker compose ps 2>&1 | grep -v warning'
stdin, stdout, stderr = client.exec_command(cmd, timeout=15)
print(f'\n=== Container Status ===\n{stdout.read().decode()}')

print(f'\n🌐 Access URL: http://111.229.26.170:3000/?token={token}')
print('   (Open this URL in your browser - it will authenticate via cookie)')

client.close()
