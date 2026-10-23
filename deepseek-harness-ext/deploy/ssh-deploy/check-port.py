import paramiko

HOST = '111.229.26.170'
USER = 'root'
PASS = '1qaZxsw@'
DEPLOY_DIR = '/home/wei/deepseek-harness-ext/deploy'

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(hostname=HOST, username=USER, password=PASS, timeout=60, banner_timeout=60)
print('Connected!')

# Check what's using port 3080
cmd = 'ss -tlnp | grep 3080'
stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
print(f'Port 3080 usage:\n{stdout.read().decode()}')

# Check all docker containers and their ports
cmd = 'docker ps --format "{{.Names}}\t{{.Ports}}\t{{.Status}}"'
stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
print(f'Docker containers:\n{stdout.read().decode()}')

client.close()
