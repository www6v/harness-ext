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

# Check which compose services exist
print('=== Docker compose config ===')
code, out, _ = run(f'cd {EXT_DIR} && docker compose config --services 2>&1')
print(f'Services: {out}')

# Check docker-compose.yml dsh section
print('\n=== dsh service in compose ===')
code, out, _ = run(f'cd {EXT_DIR} && docker compose config dsh 2>&1 | head -20')
print(out)

# Start the container
print('\n=== Starting dsh container ===')
code, out, _ = run(f'cd {EXT_DIR} && docker compose up -d dsh 2>&1', timeout=60)
print(out)

# Wait for healthy
print('\n=== Waiting for healthy ===')
for i in range(18):
    time.sleep(10)
    code, out, _ = run(f'cd {EXT_DIR} && docker compose ps dsh --format "{{{{.Status}}}}" 2>&1')
    if 'healthy' in out:
        print(f'  HEALTHY after {(i+1)*10}s!')
        break
    print(f'  {(i+1)*10}s: {out}')
else:
    print('  Not yet healthy after 180s')

# Full status
print('\n=== Final Status ===')
code, out, _ = run(f'cd {EXT_DIR} && docker compose ps 2>&1')
print(out)

code, out, _ = run(f'cd {EXT_DIR} && docker compose logs dsh --tail=5 2>&1')
print(f'\nLogs:\n{out}')

# Get token
code, token_line, _ = run(f'cd {EXT_DIR} && docker compose logs dsh 2>&1 | grep -oP "token=[A-Za-z0-9_-]+" | head -1')
if token_line:
    print(f'\n*** Access URL: http://124.221.28.203:3080/?{token_line} ***')

# API tests
print('\n=== API tests ===')
code, out, _ = run('curl -sf -o /dev/null -w "%{http_code}" -H "Host: 124.221.28.203:3080" http://127.0.0.1:3080/')
print(f'Web page: HTTP {out}')

code, out, _ = run('curl -sf -o /dev/null -w "%{http_code}" -H "Host: 124.221.28.203:3080" -H "Content-Type: application/json" -X POST -d \'{"method":"settings/describe","payload":{"args":{}}}\' http://127.0.0.1:3080/api/settings/describe')
print(f'Settings API: HTTP {out}')

code, out, _ = run('curl -sf -o /dev/null -w "%{http_code}" -H "Host: 124.221.28.203:3080" http://127.0.0.1:3080/api/llm/listProviders')
print(f'listProviders API: HTTP {out}')

client.close()
print('\nDone!')
