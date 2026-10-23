#!/usr/bin/env python3
"""
Upload deployment files to remote server via SFTP
"""

import paramiko
import os

# Configuration
HOST = "111.229.26.170"
USERNAME = "root"
PASSWORD = "1qaZxsw@"
REMOTE_DIR = "/home/wei/deepseek-harness-ext/deploy"

# Files to upload
FILES = [
    "Dockerfile",
    "Dockerfile.optimized",
    "docker-compose.yml",
    "docker-compose.dev.yml",
    ".dockerignore",
    "deploy.sh",
    "ssh-deploy-bg.py",
]

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def print_colored(text, color="blue"):
    colors = {
        "blue": "\033[0;34m",
        "green": "\033[0;32m",
        "yellow": "\033[1;33m",
        "red": "\033[0;31m",
        "reset": "\033[0m"
    }
    print(f"{colors.get(color, '')}{text}{colors['reset']}")

def upload_files():
    print_colored(f"Connecting to {HOST}...", "blue")

    transport = paramiko.Transport((HOST, 22))
    transport.connect(username=USERNAME, password=PASSWORD)
    sftp = paramiko.SFTPClient.from_transport(transport)

    try:
        for filename in FILES:
            local_path = os.path.join(SCRIPT_DIR, filename)
            remote_path = f"{REMOTE_DIR}/{filename}"

            if os.path.exists(local_path):
                print_colored(f"Uploading {filename}...", "blue")
                sftp.put(local_path, remote_path)
                print_colored(f"  ✓ {filename} uploaded", "green")
            else:
                print_colored(f"  ! {filename} not found locally, skipping", "yellow")

        print_colored("\nAll files uploaded!", "green")

    finally:
        sftp.close()
        transport.close()

if __name__ == "__main__":
    upload_files()
