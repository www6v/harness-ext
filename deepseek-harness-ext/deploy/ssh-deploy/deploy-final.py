#!/usr/bin/env python3
"""
SSH Remote Deployment - Run the build in background on remote server
Final version with full monitoring
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
    stdin, stdout, stderr = client.exec_command(command, timeout=timeout)

    for line in stdout:
        print(line, end='')
        sys.stdout.flush()

    error = stderr.read().decode('utf-8')
    if error:
        print_colored(f"Error: {error}", "red")

    return stdout.channel.recv_exit_status() == 0

def wait_for_build(client, max_wait=3600, check_interval=60):
    """Wait for build to complete, checking periodically"""
    waited = 0

    while waited < max_wait:
        # Check if build process is still running
        stdin, stdout, stderr = client.exec_command(
            "pgrep -f 'docker compose build' > /dev/null && echo 'running' || echo 'done'",
            timeout=30
        )
        result = stdout.read().decode('utf-8').strip()

        # Show last few lines of log
        stdin, stdout, stderr = client.exec_command("tail -5 /tmp/dsh-build.log 2>/dev/null || echo 'No log yet'", timeout=30)
        progress = stdout.read().decode('utf-8').strip()

        if result == 'done':
            print_colored(f"\n✓ Build completed after {waited//60} minutes!", "green")
            return True

        print_colored(f"⏳ Building... ({waited//60} min elapsed) - {progress[-80:] if len(progress) > 80 else progress}", "yellow")
        time.sleep(check_interval)
        waited += check_interval

    print_colored(f"\n! Build timeout after {max_wait//60} minutes", "red")
    return False

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
        ssh_run(client, f"cd {REMOTE_DIR} && cp Dockerfile.optimized Dockerfile", timeout=30)

        # Step 3: Start build in background
        print_colored("\n=== Step 3: Starting background build ===", "blue")
        build_cmd = f"""cd {REMOTE_DIR} && \\
export DOCKER_BUILDKIT=1 && \\
export COMPOSE_DOCKER_CLI_BUILD=1 && \\
nohup docker compose build --progress=plain > /tmp/dsh-build.log 2>&1 & \\
echo "Build started with PID: $!" """
        ssh_run(client, build_cmd, timeout=30)

        print_colored("\nBuild started in background. Waiting 15 seconds...", "yellow")
        time.sleep(15)

        # Step 4: Check build started correctly
        print_colored("\n=== Step 4: Checking build status ===", "blue")
        ssh_run(client, "head -30 /tmp/dsh-build.log 2>/dev/null || echo 'Log not ready yet'", timeout=60)

        # Wait and monitor
        print_colored("\n=== Monitoring build progress... ===", "blue")
        build_success = wait_for_build(client, max_wait=3600, check_interval=120)

        # Step 5: Show final result
        print_colored("\n=== Build Log (last 50 lines) ===", "blue")
        ssh_run(client, "tail -50 /tmp/dsh-build.log", timeout=60)

        if not build_success:
            print_colored("\nBuild did not complete within timeout. Check /tmp/dsh-build.log for details.", "yellow")
            print_colored("You can continue monitoring with: tail -f /tmp/dsh-build.log", "blue")
            return 1

        # Step 6: Start containers
        print_colored("\n=== Step 6: Starting containers ===", "blue")
        ssh_run(client, f"cd {REMOTE_DIR} && docker compose up -d", timeout=120)

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

    except paramiko.AuthenticationException:
        print_colored("Authentication failed! Check username/password.", "red")
        return 1
    except paramiko.SSHException as e:
        print_colored(f"SSH Error: {e}", "red")
        return 1
    except Exception as e:
        print_colored(f"Error: {e}", "red")
        return 1
    finally:
        client.close()
        print_colored("\nSSH connection closed.", "blue")

if __name__ == "__main__":
    sys.exit(main())
