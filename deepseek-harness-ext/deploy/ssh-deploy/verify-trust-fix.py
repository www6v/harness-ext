"""Verify the 403 fix by simulating browser requests WITH auth token."""
import paramiko

HOST = '111.229.26.170'
USER = 'root'
PASS = '1qaZxsw@'
DEPLOY_DIR = '/home/wei/deepseek-harness-ext/deploy'

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(hostname=HOST, username=USER, password=PASS, timeout=60, banner_timeout=60)
print('Connected!')

# Get the auth token from logs
cmd = f'cd {DEPLOY_DIR} && docker compose logs dsh 2>&1 | grep -oP "token=[A-Za-z0-9_-]+" | head -1'
stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
token_line = stdout.read().decode().strip()
token = token_line.replace('token=', '') if token_line else ''
print(f'Token: {token}')

if not token:
    print('ERROR: Could not find token in logs')
    client.close()
    exit(1)

# First, get the index page with token to establish auth cookie
print('\n=== Step 1: GET /?token=... (establish auth) ===')
cmd = f'curl -sf -c /tmp/dsh-cookies.txt -D /tmp/dsh-headers.txt -o /dev/null -w "HTTP %{{http_code}}" "http://127.0.0.1:3080/?token={token}" -H "Host: 111.229.26.170:3080"'
stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
print(f'Result: {stdout.read().decode().strip()}')

# Show cookies
cmd = 'cat /tmp/dsh-cookies.txt 2>/dev/null || echo "no cookies"'
stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
print(f'Cookies: {stdout.read().decode().strip()}')

# Now test API with auth cookie + trusted host header
print('\n=== Step 2: POST /api/llm/listProviders (with cookie + trusted host) ===')
cmd = f'''curl -sf -b /tmp/dsh-cookies.txt -o /tmp/dsh-api-result.txt -w "HTTP %{{http_code}}" \
  -H "Host: 111.229.26.170:3080" \
  -H "Origin: http://111.229.26.170:3080" \
  -H "Content-Type: application/json" \
  -X POST \
  -d '{{"rpcId":"test-1","method":"llm/listProviders","payload":{{"args":{{}}}}}}' \
  "http://127.0.0.1:3080/api/llm/listProviders"'''
stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
http_code = stdout.read().decode().strip()
print(f'HTTP status: {http_code}')

cmd = 'cat /tmp/dsh-api-result.txt 2>/dev/null | head -c 500'
stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
result = stdout.read().decode().strip()
print(f'Response body (first 500 chars): {result}')

# Also test agentPresets/list
print('\n=== Step 3: POST /api/agentPresets/list ===')
cmd = f'''curl -sf -b /tmp/dsh-cookies.txt -o /tmp/dsh-api-result2.txt -w "HTTP %{{http_code}}" \
  -H "Host: 111.229.26.170:3080" \
  -H "Origin: http://111.229.26.170:3080" \
  -H "Content-Type: application/json" \
  -X POST \
  -d '{{"rpcId":"test-2","method":"agentPresets/list","payload":{{"args":{{}}}}}}' \
  "http://127.0.0.1:3080/api/agentPresets/list"'''
stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
http_code2 = stdout.read().decode().strip()
print(f'HTTP status: {http_code2}')

cmd = 'cat /tmp/dsh-api-result2.txt 2>/dev/null | head -c 500'
stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
result2 = stdout.read().decode().strip()
print(f'Response body (first 500 chars): {result2}')

# Summary
print('\n=== SUMMARY ===')
if '200' in http_code and '200' in http_code2:
    print('✅ FIX VERIFIED: Both API endpoints return 200 (no more 403)')
elif '403' in http_code or '403' in http_code2:
    print('❌ STILL 403: Trust fence still rejecting')
else:
    print(f'⚠️  Mixed results: listProviders={http_code}, agentPresets/list={http_code2}')

client.close()
