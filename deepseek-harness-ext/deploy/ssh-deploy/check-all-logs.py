#!/usr/bin/env python3
"""Check container status on remote server"""
import paramiko

HOST = "111.229.26.170"
USER = "root"
PASS = "1qaZxsw@"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

try:
    print(f"Connecting to {HOST}...")
    client.connect(hostname=HOST, username=USER, password=PASS, timeout=30)
    print("Connected!\n")

    # Full logs from both containers
    print("=== dsh logs ===\n")
    cmd = "cd /home/wei/deepseek-harness-ext/deploy && docker compose logs dsh --tail=80"
    stdin, stdout, stderr = client.exec_command(cmd, timeout=60)
    output = stdout.read().decode('utf-8')
    print(output if output else "(no output)")
    err = stderr.read().decode('utf-8')
    if err:
        print("Errors:", err)

finally:
    client.close()
