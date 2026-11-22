#!/usr/bin/env python3
"""Codex WebSocket ↔ stdio Bridge.

Bridges JSON-RPC messages between the Codex Python SDK (which communicates
over stdio) and a remote `codex app-server` listening on a WebSocket.

Usage:
    python ws_bridge.py ws://HOST:PORT [--token TOKEN]

The SDK then uses:
    CodexConfig(launch_args_override=("python", "ws_bridge.py", "ws://HOST:PORT"))

The bridge:
    1. Connects to the remote WebSocket (sends auth header if --token provided)
    2. Forwards stdin → WebSocket (JSON-RPC requests from SDK → app-server)
    3. Forwards WebSocket → stdout (JSON-RPC responses from app-server → SDK)
    4. Stderr from the remote side is forwarded to local stderr
    5. Exits when the WebSocket closes or stdin reaches EOF
"""

from __future__ import annotations

import argparse
import asyncio
import os
import signal
import sys
import threading
from typing import Optional


class WsBridge:
    """Bidirectional proxy between stdio and a WebSocket."""

    def __init__(self, ws_url: str, token: Optional[str] = None) -> None:
        self._ws_url = ws_url
        self._token = token
        self._loop: asyncio.AbstractEventLoop | None = None

    def run(self) -> int:
        """Run the bridge (blocking). Uses a dedicated asyncio event loop in a thread."""
        self._loop = asyncio.new_event_loop()

        try:
            self._loop.run_until_complete(self._connect_and_bridge())
        except (ConnectionRefusedError, OSError) as exc:
            print(f"[ws_bridge] Connection failed: {exc}", file=sys.stderr)
            return 1
        except KeyboardInterrupt:
            pass
        finally:
            self._loop.close()

        return 0

    async def _connect_and_bridge(self) -> None:
        import websockets
        from websockets.asyncio.client import ClientConnection

        # Build headers
        extra_headers = {}
        if self._token:
            extra_headers["Authorization"] = f"Bearer {self._token}"
            print(f"[ws_bridge] Connecting to {self._ws_url} with auth token", file=sys.stderr)
        else:
            print(f"[ws_bridge] Connecting to {self._ws_url} (no auth)", file=sys.stderr)

        async for conn in websockets.connect(
            self._ws_url,
            additional_headers=extra_headers if extra_headers else None,
            ping_interval=30,
            ping_timeout=10,
            close_timeout=5,
        ):
            print(f"[ws_bridge] Connected", file=sys.stderr)
            try:
                await self._bridge(conn)
            except websockets.ConnectionClosed:
                print(f"[ws_bridge] Connection closed", file=sys.stderr)
                break

    async def _bridge(self, conn: ClientConnection) -> None:
        """Relay messages between stdin and the WebSocket."""

        async def ws_to_stdout() -> None:
            """Forward WebSocket messages → stdout."""
            try:
                async for message in conn:
                    if isinstance(message, bytes):
                        message = message.decode("utf-8")
                    sys.stdout.write(message)
                    sys.stdout.flush()
            except asyncio.CancelledError:
                pass
            except Exception:
                pass

        async def stdin_to_ws() -> None:
            """Forward stdin lines → WebSocket."""
            reader = asyncio.StreamReader()
            protocol = asyncio.StreamReaderProtocol(reader)
            await self._loop.connect_read_pipe(lambda: protocol, sys.stdin)

            try:
                while True:
                    line = await reader.readline()
                    if not line:  # EOF
                        print(f"[ws_bridge] stdin closed, closing WebSocket", file=sys.stderr)
                        await conn.close()
                        break
                    await conn.send(line.decode("utf-8").rstrip("\n"))
            except asyncio.CancelledError:
                pass
            except Exception:
                pass

        # Run both directions concurrently
        ws_task = asyncio.ensure_future(ws_to_stdout())
        stdin_task = asyncio.ensure_future(stdin_to_ws())

        done, pending = await asyncio.wait(
            [ws_task, stdin_task],
            return_when=asyncio.FIRST_COMPLETED,
        )

        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Codex WebSocket ↔ stdio Bridge")
    parser.add_argument("url", help="WebSocket URL (e.g., ws://host:8765)")
    parser.add_argument("--token", "-t", help="Bearer token for WebSocket auth", default=None)
    parser.add_argument("--token-file", help="Read token from file", default=None)
    args = parser.parse_args()

    token = args.token
    if args.token_file:
        try:
            with open(args.token_file) as f:
                token = f.read().strip()
        except OSError as exc:
            print(f"[ws_bridge] Cannot read token file: {exc}", file=sys.stderr)
            return 1

    # Also read from env
    if not token:
        token = os.environ.get("CODEX_WS_TOKEN")

    bridge = WsBridge(args.url, token=token)

    # Handle SIGTERM/SIGINT gracefully
    signal.signal(signal.SIGINT, lambda *_: sys.exit(0))
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))

    return bridge.run()


if __name__ == "__main__":
    sys.exit(main())