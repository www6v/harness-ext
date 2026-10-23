#!/usr/bin/env python3
"""
SSH Remote Deployment - Run the build in background on remote server
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
    print_colored(f"Running: {command[:100]}...", "blue")
    stdin, stdout, stderr = client.exec_command(command, timeout=timeout)

    for line in stdout:
        print(line, end='')
        sys.stdout.flush()

    error = stderr.read().decode('utf-8')
    if error:
        print_colored(f"Error: {error}", "red")

    return stdout.channel.recv_exit_status() == 0

def main():
    print_colored("="*60, "blue")
    print_colored("DeepSeek Harness Remote Deployment", "blue")
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

        # Step 1: Navigate to deploy directory
        print_colored("\n=== Step 1: Setting up environment ===", "blue")
        ssh_run(client, f"cd {REMOTE_DIR}", timeout=30)

        # Step 2: Use optimized Dockerfile
        print_colored("\n=== Step 2: Using optimized Dockerfile ===", "blue")
        ssh_run(client, "cd /home/wei/deepseek-harness-ext/deploy && cp Dockerfile.optimized Dockerfile", timeout=30)

        # Step 3: Start build in background
        print_colored("\n=== Step 3: Starting background build ===", "blue")
        build_cmd = """cd /home/wei/deepseek-harness-ext/deploy && \
export DOCKER_BUILDKIT=1 && \
export COMPOSE_DOCKER_CLI_BUILD=1 && \
nohup docker compose build --progress=plain > /tmp/dsh-build.log 2>&1 & \
echo "Build PID: $!" """
        ssh_run(client, build_cmd, timeout=30)

        print_colored("\nBuild started in background. Waiting 10 seconds to check status...", "yellow")
        time.sleep(10)

        # Step 4: Check build progress
        print_colored("\n=== Step 4: Checking build progress ===", "blue")
        ssh_run(client, "head -50 /tmp/dsh-build.log", timeout=60)

        # Wait and monitor
        print_colored("\n=== Monitoring build progress... ===", "blue")
        max_wait = 1800  # 30 minutes
        wait_interval = 120  # Check every 2 minutes
        waited = 0

        while waited < max_wait:
            time.sleep(wait_interval)
            waited += wait_interval

            # Check if build process is still running
            stdin, stdout, stderr = client.exec_command(
                "pgrep -f 'docker compose build' > /dev/null && echo 'running' || echo 'done'",
                timeout=30
            )
            result = stdout.read().decode('utf-8').strip()

            # Show progress
            stdin, stdout, stderr = client.exec_command("tail -10 /tmp/dsh-build.log", timeout=30)
            progress = stdout.read().decode('utf-8')

            if result == 'done':
                print_colored(f"\n✓ Build completed after {waited//60} minutes!", "green")
                print(progress)
                break
            else:
                print_colored(f"⏳ Building... ({waited//60} min elapsed)", "yellow")
                print(progress)

        # Step 5: Show final result
        print_colored("\n=== Build Log (last 50 lines) ===", "blue")
        ssh_run(client, "tail -50 /tmp/dsh-build.log", timeout=60)

        # Step 6: Start containers
        print_colored("\n=== Step 6: Starting containers ===", "blue")
        ssh_run(client, "cd /home/wei/deepseek-harness-ext/deploy && docker compose up -d", timeout=120)

        # Wait for containers to start
        time.sleep(5)

        # Step 7: Show status
        print_colored("\n=== Container Status ===", "blue")
        ssh_run(client, "docker compose ps", timeout=30)

        # Step 8: Show logs
        print_colored("\n=== Recent Logs ===", "blue")
        ssh_run(client, "docker compose logs --tail=20", timeout=60)

        print_colored("\n" + "="*60, "green")
        print_colored("Deployment completed!", "green")
        print_colored("="*60, "green")
        print_colored(f"\nFull build log: /tmp/dsh-build.log", "blue")
        print_colored("Container logs: docker compose logs -f", "blue")

        return 0

    except Exception as e:
        print_colored(f"Error: {e}", "red")
        return 1
    finally:
        client.close()

if __name__ == "__main__":
    sys.exit(main())
