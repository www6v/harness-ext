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

    cmd = "cd /home/wei/deepseek-harness-ext/deploy && docker compose ps"
    print(f"Running: {cmd}\n")

    stdin, stdout, stderr = client.exec_command(cmd, timeout=60)

    output = stdout.read().decode('utf-8')
    error = stderr.read().decode('utf-8')

    print(output)
    if error:
        print("Errors:", error)

finally:
    client.close()
