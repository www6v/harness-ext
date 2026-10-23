import paramiko
import sys
import time

HOST = '111.229.26.170'
USER = 'root'
PASS = '1qaZxsw@'
DEPLOY_DIR = '/home/wei/deepseek-harness-ext/deploy'

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(hostname=HOST, username=USER, password=PASS, timeout=120, banner_timeout=120)
print('Connected!')

# Build with full error output
print('Running docker compose build with full output...')
cmd = f'cd {DEPLOY_DIR} && docker compose --progress plain build --no-cache dsh 2>&1'
stdin, stdout, stderr = client.exec_command(cmd, timeout=1800)

# Read output and look for errors
in_build = False
error_lines = []
last_lines = []
for line in iter(stdout.readline, ''):
    stripped = line.strip()
    if stripped:
        last_lines.append(stripped)
        if len(last_lines) > 50:
            last_lines.pop(0)
    if 'error TS' in stripped or 'ERROR' in stripped or 'Error:' in stripped:
        error_lines.append(stripped)
    if any(k in stripped for k in ['DONE', 'CACHED', 'exporting', 'Step']):
        print(stripped)
        sys.stdout.flush()

exit_code = stdout.channel.recv_exit_status()

print(f'\n=== LAST 30 LINES ===')
for l in last_lines[-30:]:
    print(l)

print(f'\n=== ERRORS FOUND ===')
for e in error_lines:
    print(e)

print(f'\nExit code: {exit_code}')
client.close()
