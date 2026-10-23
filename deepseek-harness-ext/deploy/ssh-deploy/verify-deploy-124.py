import paramiko
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

# Test Settings API
print('=== Settings API ===')
cmd = '''curl -sf -b /tmp/dsh-cookies.txt -w "\\nHTTP %{http_code}" \
  -H "Host: 124.221.28.203:3080" \
  -H "Content-Type: application/json" \
  -X POST \
  -d '{"method":"settings/describe","payload":{"args":{}}}' \
  "http://127.0.0.1:3080/api/settings/describe"'''
code, out, _ = run(cmd)
print(f'settings/describe: {out[:300]}')

# Test listProviders API
print('\n=== listProviders API ===')
cmd = '''curl -sf -b /tmp/dsh-cookies.txt -w "\\nHTTP %{http_code}" \
  -H "Host: 124.221.28.203:3080" \
  "http://127.0.0.1:3080/api/llm/listProviders"'''
code, out, _ = run(cmd)
print(f'listProviders: {out[:300]}')

# Test agentPresets/list API
print('\n=== agentPresets API ===')
cmd = '''curl -sf -b /tmp/dsh-cookies.txt -w "\\nHTTP %{http_code}" \
  -H "Host: 124.221.28.203:3080" \
  -H "Content-Type: application/json" \
  -X POST \
  -d '{"method":"agentPresets/list","payload":{"args":{}}}' \
  "http://127.0.0.1:3080/api/agentPresets/list"'''
code, out, _ = run(cmd)
print(f'agentPresets/list: {out[:300]}')

# Health check analysis
print('\n=== Health check ===')
code, out, _ = run('docker inspect deepseek-harness --format "{{.State.Health.Status}}" 2>/dev/null')
print(f'Health status: {out}')
code, out, _ = run('docker inspect deepseek-harness --format "{{range .State.Health.Log}}Exit={{.ExitCode}} Output={{.Output}}---{{end}}" 2>/dev/null')
logs = out.split('---')[-3:] if out else []
for log in logs:
    if log.strip():
        print(f'  {log.strip()[:200]}')

client.close()
print('\n=== Done! ===')
