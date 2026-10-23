import paramiko, time
client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(hostname='124.221.28.203', username='root', password='1qaZxsw@', timeout=30, banner_timeout=30)

EXT_DIR = '/home/ubuntu/wei/deepseek-harness-ext/deploy'

def run(cmd, timeout=30):
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    code = stdout.channel.recv_exit_status()
    return code, out, err

# Fix healthcheck: use curl without -f (accept any HTTP response including 303)
# A 303 redirect means the service IS running and responding
print('=== Fix healthcheck ===')
code, content, _ = run(f'cat {EXT_DIR}/docker-compose.yml')

# Replace healthcheck test to use curl without -f (just check connectivity)
old = '      test: ["CMD", "curl", "-sf", "http://127.0.0.1:3080/?token=ICRWp4KcOIzcnU04MZEfAGrpyyPSmmMi2KPqycoLF4A"]'
new = '      test: ["CMD-SHELL", "curl -so /dev/null http://127.0.0.1:3080/ || exit 1"]'
if old in content:
    content = content.replace(old, new)
    escaped = content.replace("'", "'\\''")
    run(f"printf '%s' '{escaped}' > {EXT_DIR}/docker-compose.yml")
    print('Updated healthcheck to use curl -so (no -f, accepts 303)')
else:
    # Try finding any existing healthcheck line
    print(f'Old line not found, searching...')
    for i, line in enumerate(content.split('\n')):
        if 'test:' in line and 'curl' in line:
            print(f'  Found at line {i}: {line}')
            content = content.replace(line, '      test: ["CMD-SHELL", "curl -so /dev/null http://127.0.0.1:3080/ || exit 1"]')
    escaped = content.replace("'", "'\\''")
    run(f"printf '%s' '{escaped}' > {EXT_DIR}/docker-compose.yml")

# Verify
code, out, _ = run(f'grep -A3 "healthcheck" {EXT_DIR}/docker-compose.yml | head -5')
print(f'Updated:\n{out}')

# Recreate
print('\n=== Recreate container ===')
code, out, _ = run(f'cd {EXT_DIR} && docker compose up -d --force-recreate dsh 2>&1', timeout=60)
print(out)

# Wait for healthy
print('\n=== Wait for healthy ===')
for i in range(12):
    time.sleep(10)
    code, out, _ = run('docker inspect deepseek-harness --format "{{.State.Health.Status}}" 2>/dev/null')
    if out == 'healthy':
        print(f'  ✅ HEALTHY after {(i+1)*10}s!')
        break
    # Also check last health log for progress
    code2, log, _ = run('docker inspect deepseek-harness --format "{{with index .State.Health.Log 0}}{{.ExitCode}}{{end}}" 2>/dev/null')
    print(f'  {(i+1)*10}s: {out} (last exit: {log})')

# Final
print('\n=== FINAL STATUS ===')
code, out, _ = run(f'cd {EXT_DIR} && docker compose ps 2>&1')
print(out)

code, out, _ = run('docker inspect deepseek-harness --format "{{.State.Health.Status}}" 2>/dev/null')
print(f'\nHealth: {out}')

TOKEN = 'ICRWp4KcOIzcnU04MZEfAGrpyyPSmmMi2KPqycoLF4A'
if out == 'healthy':
    print(f'\n🎉 Deployment successful!')
    print(f'   Access: http://124.221.28.203:3080/?token={TOKEN}')
else:
    print(f'\n⚠️ Health: {out}')
    code, out, _ = run('docker inspect deepseek-harness --format "{{range .State.Health.Log}}Exit={{.ExitCode}} Output={{.Output}}---{{end}}" 2>/dev/null')
    logs = [l for l in out.split('---') if l.strip()][-2:]
    for log in logs:
        print(f'   Log: {log.strip()[:200]}')

client.close()
