import paramiko

HOST = '111.229.26.170'
USER = 'root'
PASS = '1qaZxsw@'
DEPLOY_DIR = '/home/wei/deepseek-harness-ext/deploy'

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(hostname=HOST, username=USER, password=PASS, timeout=60, banner_timeout=60)

# Check what process is on 3080
cmd = 'ps -p 958 -o pid,ppid,user,cmd --no-headers 2>/dev/null || echo "process not found"'
stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
print(f'Process 958:\n{stdout.read().decode().strip()}')

# Check parent process
cmd = 'ps -p 958 -o ppid= 2>/dev/null | xargs -I{} ps -p {} -o pid,cmd --no-headers 2>/dev/null'
stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
print(f'\nParent process:\n{stdout.read().decode().strip()}')

# Check the cmdline
cmd = 'cat /proc/958/cmdline 2>/dev/null | tr "\\0" " "'
stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
print(f'\nCmdline: {stdout.read().decode().strip()}')

# Check working directory
cmd = 'ls -la /proc/958/cwd 2>/dev/null'
stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
print(f'\nCWD: {stdout.read().decode().strip()}')

# Check if it's the old deepseek-harness
cmd = 'cat /proc/958/environ 2>/dev/null | tr "\\0" "\\n" | grep -E "DSH_|DEEPSEEK|HOME" | head -10'
stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
print(f'\nEnv:\n{stdout.read().decode().strip()}')

client.close()
