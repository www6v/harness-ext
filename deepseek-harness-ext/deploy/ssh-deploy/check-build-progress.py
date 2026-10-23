import paramiko
client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(hostname='124.221.28.203', username='root', password='1qaZxsw@', timeout=30, banner_timeout=30)

EXT_DIR = '/home/ubuntu/wei/deepseek-harness-ext/deploy'

cmds = [
    ('compose ps', f'cd {EXT_DIR} && docker compose ps 2>&1'),
    ('port 3080', 'ss -tlnp | grep 3080 || echo "PORT FREE"'),
    ('deepseek containers', 'docker ps -a --filter "name=deepseek" --format "{{.Names}} {{.Status}}" 2>&1'),
]
for label, cmd in cmds:
    stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    print(f'=== {label} ===\n{out or err}\n')

client.close()
