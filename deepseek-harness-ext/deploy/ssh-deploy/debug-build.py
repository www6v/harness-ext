import paramiko

HOST = '111.229.26.170'
USER = 'root'
PASS = '1qaZxsw@'
DEPLOY_DIR = '/home/wei/deepseek-harness-ext/deploy'

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(hostname=HOST, username=USER, password=PASS, timeout=120, banner_timeout=120)
print('Connected!')

# Re-run the build with full output to see the actual error
print('Running docker build with full output...')
cmd = f'cd {DEPLOY_DIR} && docker compose --progress plain build --no-cache dsh 2>&1 | grep -E "error|Error|ERROR|failed|Failed|FAIL" | head -20'
stdin, stdout, stderr = client.exec_command(cmd, timeout=1800)
errors = stdout.read().decode().strip()
print(f'Errors found:\n{errors}')

# Also try building just to see the full output of the failing step
print('\n=== Running build step 14 directly ===')
cmd = f'cd {DEPLOY_DIR} && docker build --progress plain --target build -f Dockerfile ../../deepseek-harness 2>&1 | tail -50'
stdin, stdout, stderr = client.exec_command(cmd, timeout=1800)
output = stdout.read().decode().strip()
print(output)

client.close()
