#!/usr/bin/env python3
"""Probe new server environment at 124.221.28.203"""
import paramiko

HOST = '124.221.28.203'
USER = 'root'
PASS = '1qaZxsw@'

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(hostname=HOST, username=USER, password=PASS, timeout=30, banner_timeout=30)
print('Connected!')

checks = [
    ('OS', 'cat /etc/os-release | head -3'),
    ('Docker', 'docker --version 2>/dev/null || echo "NOT INSTALLED"'),
    ('Docker Compose', 'docker compose version 2>/dev/null || echo "NOT INSTALLED"'),
    ('Disk', 'df -h / | tail -1'),
    ('Memory', 'free -h | head -2'),
    ('CPU', 'nproc'),
    ('Existing dirs', 'ls -la /home/ubuntu/wei/ 2>/dev/null || echo "DIR NOT FOUND"'),
    ('Docker daemon', 'systemctl is-active docker 2>/dev/null || echo "NOT ACTIVE"'),
    ('Docker info', 'docker info 2>/dev/null | grep -E "Registry Mirrors|Storage Driver|Runtimes" || echo "no info"'),
    ('Port 3080', 'ss -tlnp | grep 3080 || echo "PORT FREE"'),
]

for label, cmd in checks:
    stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    print(f'\n=== {label} ===')
    print(out if out else err if err else '(empty)')

client.close()
