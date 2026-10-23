import paramiko

HOST = '111.229.26.170'
USER = 'root'
PASS = '1qaZxsw@'
DEPLOY_DIR = '/home/wei/deepseek-harness-ext/deploy'

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(hostname=HOST, username=USER, password=PASS, timeout=120, banner_timeout=120)
print('Connected!')

token = 'UZMd00mIUXgz90ABF9-Ltlqa9eLR4LCqCKsUJxJczTU'

# 1. Verify HTML injection WITH auth token
print('=== 1. Check HTML injection with auth ===')
cmd = f'''curl -sf "http://127.0.0.1:3080/?token={token}" -H "Host: 111.229.26.170:3080" | grep -o "__DSH_TRUSTED_REMOTE__" || echo "NOT FOUND"'''
stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
print(f'Injection: {stdout.read().decode().strip()}')

# 2. Test API with public IP host (simulate browser)
print('\n=== 2. Test API with auth + trusted host ===')
# First get auth cookie
cmd = f'curl -sf -c /tmp/cookies.txt "http://127.0.0.1:3080/?token={token}" -H "Host: 111.229.26.170:3080" -o /dev/null -w "%{{http_code}}"'
stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
print(f'Auth: {stdout.read().decode().strip()}')

# Test listProviders
cmd = '''curl -sf -b /tmp/cookies.txt -o /dev/null -w "%{http_code}" \
  -H "Host: 111.229.26.170:3080" \
  -H "Origin: http://111.229.26.170:3080" \
  -H "Content-Type: application/json" \
  -X POST \
  -d '{"type":"client-request","rpcId":"t1","method":"llm/listProviders","payload":{"args":{}}}' \
  "http://127.0.0.1:3080/api/llm/listProviders"'''
stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
print(f'listProviders: {stdout.read().decode().strip()}')

# Test settings/describe (this is what the settings page uses)
cmd = '''curl -sf -b /tmp/cookies.txt -o /tmp/settings-result.txt -w "%{http_code}" \
  -H "Host: 111.229.26.170:3080" \
  -H "Origin: http://111.229.26.170:3080" \
  -H "Content-Type: application/json" \
  -X POST \
  -d '{"type":"client-request","rpcId":"t2","method":"settings/describe","payload":{"args":{}}}' \
  "http://127.0.0.1:3080/api/settings/describe"'''
stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
http_code = stdout.read().decode().strip()
print(f'settings/describe: {http_code}')

cmd = 'cat /tmp/settings-result.txt 2>/dev/null | head -c 300'
stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
result = stdout.read().decode().strip()
print(f'Response: {result}')

# Summary
print('\n=== SUMMARY ===')
if '200' in http_code:
    print('✅ settings/describe returns 200 — settings will load correctly')
else:
    print(f'⚠️  settings/describe returned {http_code}')

client.close()
