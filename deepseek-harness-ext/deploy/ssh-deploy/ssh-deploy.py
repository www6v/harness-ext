#!/usr/bin/env python3
"""
SSH Remote Deployment Script for DeepSeek Harness
"""

import paramiko
import sys
import time

# Configuration
HOST = "111.229.26.170"
USERNAME = "root"
PASSWORD = "1qaZxsw@"
REMOTE_DIR = "/home/wei/deepseek-harness-ext/deploy"

def print_colored(text, color="blue"):
    """Print colored output"""
    colors = {
        "blue": "\033[0;34m",
        "green": "\033[0;32m",
        "yellow": "\033[1;33m",
        "red": "\033[0;31m",
        "reset": "\033[0m"
    }
    print(f"{colors.get(color, '')}{text}{colors['reset']}")

def ssh_execute(host, username, password, commands, timeout=600):
    """Execute commands on remote server via SSH"""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    print_colored(f"Connecting to {host}...", "blue")

    try:
        client.connect(
            hostname=host,
            username=username,
            password=password,
            timeout=30,
            allow_agent=False,
            look_for_keys=False
        )
        print_colored("Connected successfully!", "green")

        # Combine all commands
        full_command = " && ".join(commands)

        print_colored("\n" + "="*50, "blue")
        print_colored("Executing deployment commands", "blue")
        print_colored("="*50 + "\n", "blue")

        # Execute command
        stdin, stdout, stderr = client.exec_command(full_command, timeout=timeout)

        # Read output in real-time
        while True:
            line = stdout.readline()
            if not line:
                break
            print(line, end='')
            sys.stdout.flush()

        # Check for errors
        error = stderr.read().decode('utf-8')
        if error:
            print_colored("\nErrors occurred:", "red")
            print(error)

        exit_status = stdout.channel.recv_exit_status()
        return exit_status == 0

    except paramiko.AuthenticationException:
        print_colored("Authentication failed! Check username/password.", "red")
        return False
    except paramiko.SSHException as e:
        print_colored(f"SSH Error: {e}", "red")
        return False
    except Exception as e:
        print_colored(f"Error: {e}", "red")
        return False
    finally:
        client.close()
        print_colored("\nSSH connection closed.", "blue")

def main():
    print_colored("="*60, "blue")
    print_colored("DeepSeek Harness Remote Deployment", "blue")
    print_colored("="*60, "blue")

    # Deployment commands
    commands = [
        f"cd {REMOTE_DIR}",
        "chmod +x *.sh",
        "echo '=== Environment Setup ==='",
        "export DOCKER_BUILDKIT=1",
        "export COMPOSE_DOCKER_CLI_BUILD=1",
        "echo 'DOCKER_BUILDKIT=1'",
        "echo 'COMPOSE_DOCKER_CLI_BUILD=1'",
        "echo ''",
        "echo '=== Building Docker Image ==='",
        "docker compose build --progress=plain",
        "echo ''",
        "echo '=== Starting Containers ==='",
        "docker compose up -d",
        "sleep 5",
        "echo ''",
        "echo '=== Container Status ==='",
        "docker compose ps",
        "echo ''",
        "echo '=== Recent Logs ==='",
        "docker compose logs --tail=30",
        "echo ''",
        "echo '=== Deployment Complete ==='"
    ]

    success = ssh_execute(
        host=HOST,
        username=USERNAME,
        password=PASSWORD,
        commands=commands,
        timeout=600  # 10 minutes timeout for build
    )

    if success:
        print_colored("\n✓ Deployment completed successfully!", "green")
        return 0
    else:
        print_colored("\n✗ Deployment failed!", "red")
        return 1

if __name__ == "__main__":
    sys.exit(main())
