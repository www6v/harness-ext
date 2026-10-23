import paramiko

HOST = '111.229.26.170'
USER = 'root'
PASS = '1qaZxsw@'
DEPLOY_DIR = '/home/wei/deepseek-harness-ext/deploy'

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(hostname=HOST, username=USER, password=PASS, timeout=60, banner_timeout=60)
print('Connected!')

# Check container health
cmd = f'cd {DEPLOY_DIR} && docker compose ps 2>&1'
stdin, stdout, stderr = client.exec_command(cmd, timeout=30)
print('=== Container Status ===')
print(stdout.read().decode('utf-8'))

# Check recent logs
cmd = f'cd {DEPLOY_DIR} && docker compose logs dsh --tail=20 2>&1'
stdin, stdout, stderr = client.exec_command(cmd, timeout=30)
print('=== Recent Logs (last 20) ===')
print(stdout.read().decode('utf-8'))

# Health check via curl
cmd = 'curl -sf http://127.0.0.1:3000/ | head -5'
stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
out = stdout.read().decode('utf-8')
err = stderr.read().decode('utf-8')
print('=== Health Check (curl localhost:3000) ===')
if out:
    print(out[:500])
else:
    print(f'No response or error: {err}')

# Check listening ports
cmd = 'ss -tlnp | grep 3000'
stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
print('\n=== Listening on port 3000 ===')
print(stdout.read().decode('utf-8'))

client.close()
