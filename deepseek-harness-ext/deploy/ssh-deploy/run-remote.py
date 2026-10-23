#!/usr/bin/env python3
"""
Simple SSH command executor using subprocess
"""
import subprocess
import sys

HOST = "111.229.26.170"
USER = "root"
PASS = "1qaZxsw@"

# Read the script
with open("remote-deploy.sh", "r") as f:
    script = f.read()

# Use ssh with password via environment
import os
os.environ["SSHPASS"] = PASS

cmd = ["sshpass", "-d", "0", "ssh", "-o", "StrictHostKeyChecking=no",
       f"{USER}@{HOST}", "bash -s", "<", "/home/wei/deepseek-harness-ext/deploy/remote-deploy.sh"]

# Actually just run the script that's already uploaded
run_cmd = ["sshpass", "-d", "0", "ssh", "-o", "StrictHostKeyChecking=no",
           f"{USER}@{HOST}", "cd /home/wei/deepseek-harness-ext/deploy && bash remote-deploy.sh"]

print(f"Running: {' '.join(run_cmd)}")
result = subprocess.run(run_cmd, capture_output=True, text=True, timeout=600)

print(result.stdout)
if result.stderr:
    print(result.stderr, file=sys.stderr)

sys.exit(result.returncode)
