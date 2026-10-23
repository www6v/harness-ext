import paramiko

HOST = '111.229.26.170'
USER = 'root'
PASS = '1qaZxsw@'

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(hostname=HOST, username=USER, password=PASS, timeout=120, banner_timeout=120)
print('Connected!')

# Follow redirect to get the actual HTML page
print('=== Check HTML injection following redirect ===')
cmd = '''curl -sfL "http://127.0.0.1:3080/?token=UZMd00mIUXgz90ABF9-Ltlqa9eLR4LCqCKsUJxJczTU" \
  -H "Host: 111.229.26.170:3080" \
  -o /tmp/page.html -w "%{http_code}"'''
stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
print(f'HTTP: {stdout.read().decode().strip()}')

cmd = 'grep -c "__DSH_TRUSTED_REMOTE__" /tmp/page.html'
stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
count = stdout.read().decode().strip()
print(f'Injection occurrences: {count}')

cmd = 'grep "__DSH_TRUSTED_REMOTE__" /tmp/page.html'
stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
print(f'Line: {stdout.read().decode().strip()}')

# Also check page size
cmd = 'wc -c /tmp/page.html'
stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
print(f'Page size: {stdout.read().decode().strip()}')

client.close()
