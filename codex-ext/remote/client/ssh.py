#!/usr/bin/env python3
"""SSH connection module for Codex PoC remote deployment.

Usage:
    from ssh import RemoteHost

    with RemoteHost("124.221.28.203", user="root", password="1qaZxsw@") as host:
        result = host.run("ls -la /home/wei/")
        print(result.stdout)
"""

from __future__ import annotations

import os
import sys
import time
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class CommandResult:
    """Result of a remote command execution."""

    stdout: str
    stderr: str
    exit_code: int
    elapsed_ms: float


class RemoteHost:
    """SSH connection to a remote Linux host.

    Automatically retries on connection failure with exponential backoff.
    Uses paramiko (pure Python SSH2) — no external binaries needed.
    """

    def __init__(
        self,
        host: str,
        user: str = "root",
        password: Optional[str] = None,
        port: int = 22,
        timeout: float = 30.0,
    ):
        self._host = host
        self._port = port
        self._user = user
        self._password = password
        self._timeout = timeout
        self._client = None
        self._sftp = None

    def __enter__(self) -> "RemoteHost":
        self.connect()
        return self

    def __exit__(self, *args) -> None:
        self.close()

    def connect(self) -> None:
        """Establish SSH connection with retry."""
        import paramiko

        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            try:
                self._client = paramiko.SSHClient()
                self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                self._client.connect(
                    hostname=self._host,
                    port=self._port,
                    username=self._user,
                    password=self._password,
                    timeout=self._timeout,
                    banner_timeout=15.0,
                    auth_timeout=15.0,
                    allow_agent=False,
                    look_for_keys=False,
                )
                print(f"[SSH] Connected to {self._user}@{self._host}:{self._port}")
                return
            except Exception as e:
                print(f"[SSH] Attempt {attempt}/{max_attempts} failed: {e}", file=sys.stderr)
                if attempt == max_attempts:
                    raise
                time.sleep(2**attempt)

    def close(self) -> None:
        if self._sftp:
            self._sftp.close()
            self._sftp = None
        if self._client:
            self._client.close()
            self._client = None
            print(f"[SSH] Disconnected from {self._host}")

    @property
    def client(self):
        if self._client is None:
            raise RuntimeError("Not connected. Use `with RemoteHost(...) as host:` first.")
        return self._client

    @property
    def sftp(self):
        if self._sftp is None:
            self._sftp = self.client.open_sftp()
        return self._sftp

    def run(self, command: str, timeout: float = 120.0) -> CommandResult:
        """Execute a command on the remote host and return its result."""
        t0 = time.monotonic()
        _stdin, stdout, stderr = self.client.exec_command(command, timeout=timeout)
        elapsed = (time.monotonic() - t0) * 1000
        stdout_str = stdout.read().decode("utf-8", errors="replace")
        stderr_str = stderr.read().decode("utf-8", errors="replace")
        exit_code = stdout.channel.recv_exit_status()
        return CommandResult(
            stdout=stdout_str,
            stderr=stderr_str,
            exit_code=exit_code,
            elapsed_ms=elapsed,
        )

    def run_verbose(self, command: str, timeout: float = 120.0) -> CommandResult:
        """Run a command and print its output in real time."""
        print(f"[RUN] {command}")
        result = self.run(command, timeout=timeout)
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        print(f"[EXIT] code={result.exit_code}, elapsed={result.elapsed_ms:.0f}ms")
        return result

    def upload_file(self, local_path: str | Path, remote_path: str) -> None:
        """Upload a single file to the remote host."""
        print(f"[UPLOAD] {local_path} -> {self._host}:{remote_path}")
        self.sftp.put(str(local_path), remote_path)

    def upload_dir(self, local_dir: str | Path, remote_dir: str) -> None:
        """Recursively upload a directory to the remote host."""
        local_dir = Path(local_dir)
        print(f"[UPLOAD] {local_dir}/ -> {self._host}:{remote_dir}/")
        self._upload_tree(local_dir, remote_dir)

    def _upload_tree(self, local: Path, remote_base: str) -> None:
        try:
            self.sftp.mkdir(remote_base)
        except OSError:
            pass
        for child in local.iterdir():
            if child.is_file():
                self.sftp.put(str(child), f"{remote_base}/{child.name}")
            elif child.is_dir():
                self._upload_tree(child, f"{remote_base}/{child.name}")

    def download_file(self, remote_path: str, local_path: str | Path) -> None:
        """Download a single file from the remote host."""
        print(f"[DOWNLOAD] {self._host}:{remote_path} -> {local_path}")
        self.sftp.get(remote_path, str(local_path))

    def file_exists(self, remote_path: str) -> bool:
        try:
            self.sftp.stat(remote_path)
            return True
        except FileNotFoundError:
            return False

    def write_file(self, remote_path: str, content: str) -> None:
        """Write a string to a remote file (via a temporary upload)."""
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".tmp", delete=False, encoding="utf-8") as f:
            f.write(content)
            tmp_path = f.name
        try:
            self.upload_file(tmp_path, remote_path)
        finally:
            os.unlink(tmp_path)


def get_remote_host() -> RemoteHost:
    """Factory for the standard Codex PoC deployment target."""
    return RemoteHost(
        host=os.environ.get("CODEX_REMOTE_HOST", "124.221.28.203"),
        user=os.environ.get("CODEX_REMOTE_USER", "root"),
        password=os.environ.get("CODEX_REMOTE_PASSWORD", "1qaZxsw@"),
    )


if __name__ == "__main__":
    # Quick test: connect and check uname
    with get_remote_host() as host:
        result = host.run_verbose("uname -a && cat /etc/os-release | head -5")
        result = host.run_verbose("which docker && docker --version 2>/dev/null || echo 'Docker not found'")
        result = host.run_verbose("ls -la /home/wei/meta-harness/ 2>/dev/null || echo 'Directory /home/wei/meta-harness/ not found'")