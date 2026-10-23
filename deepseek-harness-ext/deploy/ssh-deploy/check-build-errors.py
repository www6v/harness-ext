import paramiko

HOST = '111.229.26.170'
USER = 'root'
PASS = '1qaZxsw@'
DEPLOY_DIR = '/home/wei/deepseek-harness-ext/deploy'
SOURCE_DIR = '/home/wei/deepseek-harness'

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(hostname=HOST, username=USER, password=PASS, timeout=120, banner_timeout=120)
print('Connected!')

# Run the failing build step and capture full output
print('Running build step with full error output...')
cmd = f'cd {SOURCE_DIR} && corepack enable && corepack prepare pnpm@11.7.0 --activate 2>&1 && PATH=/root/.local/share/pnpm:$PATH pnpm run build:lib:client 2>&1 | grep -E "error TS|Error" | head -30'
stdin, stdout, stderr = client.exec_command(cmd, timeout=600)
output = stdout.read().decode().strip()
print(f'Errors:\n{output}')

client.close()
