import paramiko

HOST = '111.229.26.170'
USER = 'root'
PASS = '1qaZxsw@'
SOURCE_DIR = '/home/wei/deepseek-harness'

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(hostname=HOST, username=USER, password=PASS, timeout=120, banner_timeout=120)
print('Connected!')

# Check the actual error files on server
cmd = f'grep -n "rpc" {SOURCE_DIR}/packages/test-support/client-runtime/src/assembly/test-client.ts | head -10'
stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
print('=== test-client.ts rpc references ===')
print(stdout.read().decode())

cmd = f'grep -n "rpc" {SOURCE_DIR}/packages/client/connection/tests/client-apply.client.spec.ts | head -10'
stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
print('=== client-apply.client.spec.ts rpc references ===')
print(stdout.read().decode())

# Check if ClientTransportHooks has rpc field in the server's version
cmd = f'grep -A 20 "ClientTransportHooks" {SOURCE_DIR}/packages/client/connection/src/client/index.ts | head -25'
stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
print('=== ClientTransportHooks on server ===')
print(stdout.read().decode())

client.close()
