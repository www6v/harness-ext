#!/usr/bin/env python3
"""
SSH Remote Deployment Script - Uses nohup to run build in background
This avoids SSH timeout issues by running the long build process in background
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
    colors = {
        "blue": "\033[0;34m",
        "green": "\033[0;32m",
        "yellow": "\033[1;33m",
        "red": "\033[0;31m",
        "reset": "\033[0m"
    }
    print(f"{colors.get(color, '')}{text}{colors['reset']}")

def ssh_run(client, command, timeout=60):
    """Run a command and print output"""
    print_colored(f"Running: {command[:80]}...", "blue")
    stdin, stdout, stderr = client.exec_command(command, timeout=timeout)

    output = []
    for line in stdout:
        print(line, end='')
        output.append(line)
        sys.stdout.flush()

    error = stderr.read().decode('utf-8')
    if error:
        print_colored(f"Error: {error}", "red")

    return stdout.channel.recv_exit_status() == 0, ''.join(output)

def main():
    print_colored("="*60, "blue")
    print_colored("DeepSeek Harness Remote Deployment (Background Build)", "blue")
    print_colored("="*60, "blue")

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        print_colored(f"Connecting to {HOST}...", "blue")
        client.connect(
            hostname=HOST,
            username=USERNAME,
            password=PASSWORD,
            timeout=30,
            allow_agent=False,
            look_for_keys=False
        )
        print_colored("Connected successfully!", "green")

        # Step 1: Navigate and prepare
        print_colored("\n=== Step 1: Preparing environment ===", "blue")
        ssh_run(client, f"cd {REMOTE_DIR}", timeout=30)
        ssh_run(client, "chmod +x *.sh", timeout=30)

        # Step 2: Use optimized Dockerfile
        print_colored("\n=== Step 2: Setting up optimized Dockerfile ===", "blue")
        ssh_run(client, "cp Dockerfile.optimized Dockerfile", timeout=30)

        # Step 3: Pull base image first
        print_colored("\n=== Step 3: Pulling base image ===", "blue")
        ssh_run(client, "docker pull node:22-alpine", timeout=600)

        # Step 4: Start background build with nohup
        print_colored("\n=== Step 4: Starting background build ===", "blue")
        build_cmd = f"cd {REMOTE_DIR} && export DOCKER_BUILDKIT=1 && export COMPOSE_DOCKER_CLI_BUILD=1 && nohup docker compose build --progress=plain > /tmp/dsh-build.log 2>&1 &"
        ssh_run(client, build_cmd, timeout=30)

        print_colored("\nBuild started in background. Waiting 30 seconds...", "yellow")
        time.sleep(30)

        # Step 5: Check build progress
        print_colored("\n=== Step 5: Checking build progress ===", "blue")
        ssh_run(client, "tail -50 /tmp/dsh-build.log", timeout=60)

        # Wait for build to complete (check periodically)
        print_colored("\n=== Waiting for build to complete... ===", "blue")
        max_wait = 1800  # 30 minutes max
        wait_interval = 60  # Check every minute
        waited = 0

        while waited < max_wait:
            time.sleep(wait_interval)
            waited += wait_interval

            # Check if build is still running
            stdin, stdout, stderr = client.exec_command("pgrep -f 'docker compose build' || echo 'done'", timeout=30)
            result = stdout.read().decode('utf-8').strip()

            if result == 'done':
                print_colored(f"\nBuild completed after {waited//60} minutes!", "green")
                break
            else:
                print_colored(f"Still building... ({waited//60} minutes elapsed)", "yellow")
                # Show last few lines of log
                ssh_run(client, "tail -5 /tmp/dsh-build.log", timeout=30)

        # Step 6: Show final build result
        print_colored("\n=== Build Log (last 30 lines) ===", "blue")
        ssh_run(client, "tail -30 /tmp/dsh-build.log", timeout=60)

        # Step 7: Start containers
        print_colored("\n=== Step 7: Starting containers ===", "blue")
        ssh_run(client, "docker compose up -d", timeout=120)

        # Step 8: Show status
        print_colored("\n=== Container Status ===", "blue")
        ssh_run(client, "docker compose ps", timeout=30)

        print_colored("\n" + "="*60, "green")
        print_colored("Deployment completed successfully!", "green")
        print_colored("="*60, "green")
        print_colored(f"\nFull build log at: /tmp/dsh-build.log", "blue")
        print_colored("View logs with: docker compose logs -f", "blue")

        return 0

    except paramiko.AuthenticationException:
        print_colored("Authentication failed!", "red")
        return 1
    except paramiko.SSHException as e:
        print_colored(f"SSH Error: {e}", "red")
        return 1
    except Exception as e:
        print_colored(f"Error: {e}", "red")
        return 1
    finally:
        client.close()

if __name__ == "__main__":
    sys.exit(main())
