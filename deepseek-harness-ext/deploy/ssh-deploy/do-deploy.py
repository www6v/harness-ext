#!/usr/bin/env python3
"""
SSH Remote Deployment using only paramiko - no external dependencies needed on remote
"""
import paramiko
import time
import sys

HOST = "111.229.26.170"
USER = "root"
PASS = "1qaZxsw@"
DEPLOY_DIR = "/home/wei/deepseek-harness-ext/deploy"

def main():
    print("="*60)
    print("DeepSeek Harness Remote Deployment")
    print("="*60)

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        print(f"Connecting to {HOST}...")
        client.connect(hostname=HOST, username=USER, password=PASS, timeout=30)
        print("Connected!")

        # Run deployment script that's already on server
        cmd = f"cd {DEPLOY_DIR} && bash remote-deploy.sh"
        print(f"\nRunning: {cmd}\n")

        stdin, stdout, stderr = client.exec_command(cmd, timeout=3600)

        # Stream output
        while True:
            line = stdout.readline()
            if not line:
                break
            print(line, end='')
            sys.stdout.flush()

        # Check for errors
        error = stderr.read().decode('utf-8')
        if error:
            print("\nErrors:", file=sys.stderr)
            print(error, file=sys.stderr)

        exit_code = stdout.channel.recv_exit_status()

        print("\n" + "="*60)
        if exit_code == 0:
            print("Deployment completed successfully!")
        else:
            print(f"Deployment finished with exit code: {exit_code}")
        print("="*60)

        return exit_code

    except Exception as e:
        print(f"Error: {e}")
        return 1
    finally:
        client.close()

if __name__ == "__main__":
    sys.exit(main())
