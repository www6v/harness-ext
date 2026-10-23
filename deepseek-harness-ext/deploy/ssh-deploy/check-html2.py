import paramiko

HOST = '111.229.26.170'
USER = 'root'
PASS = '1qaZxsw@'

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(hostname=HOST, username=USER, password=PASS, timeout=120, banner_timeout=120)
print('Connected!')

# Step 1: Get auth cookie
print('=== Step 1: Auth ===')
cmd = 'curl -sf -c /tmp/auth-cookies.txt "http://127.0.0.1:3080/?token=UZMd00mIUXgz90ABF9-Ltlqa9eLR4LCqCKsUJxJczTU" -H "Host: 111.229.26.170:3080" -o /dev/null -w "%{http_code}"'
stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
print(f'Auth: {stdout.read().decode().strip()}')

# Step 2: Request HTML with cookie
print('\n=== Step 2: Get HTML ===')
cmd = 'curl -sf -b /tmp/auth-cookies.txt "http://127.0.0.1:3080/" -H "Host: 111.229.26.170:3080" -o /tmp/page.html -w "%{http_code}"'
stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
print(f'HTML: {stdout.read().decode().strip()}')

cmd = 'wc -c /tmp/page.html'
stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
print(f'Page size: {stdout.read().decode().strip()}')

cmd = 'grep "__DSH_TRUSTED_REMOTE__" /tmp/page.html || echo "NOT FOUND"'
stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
print(f'Injection: {stdout.read().decode().strip()}')

# Check what scripts are in the head
cmd = 'grep -o "<script>[^<]*</script>" /tmp/page.html | head -5'
stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
print(f'\nScripts in page:\n{stdout.read().decode().strip()}')

client.close()
