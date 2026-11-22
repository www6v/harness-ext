"""Codex PoC remote deployment — SSH connection module."""

from .ssh import RemoteHost, CommandResult, get_remote_host

__all__ = ["RemoteHost", "CommandResult", "get_remote_host"]