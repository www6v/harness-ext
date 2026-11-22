"""PoC: Full codex prompt execution via SSH tunnel.
Flow: initialize -> thread/start -> turn/start -> wait for turn/completed"""
import sys, os, asyncio, json, threading, socket, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ssh import RemoteHost

def create_tunnel(local_port=18765):
    host = RemoteHost("124.221.28.203", user="root", password="1qaZxsw@")
    host.connect()
    transport = host.client.get_transport()
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind(('127.0.0.1', local_port))
    server_sock.listen(5)
    print(f"[TUNNEL] 127.0.0.1:{local_port} -> remote:8765")
    running = [True]
    def accept_loop():
        server_sock.settimeout(1.0)
        while running[0]:
            try:
                client_sock, addr = server_sock.accept()
                chan = transport.open_channel('direct-tcpip', ('127.0.0.1', 8765), ('127.0.0.1', local_port))
                def forward(src, dst):
                    try:
                        while True:
                            data = src.recv(4096)
                            if not data: break
                            dst.sendall(data)
                    except: pass
                    finally:
                        try: src.close()
                        except: pass
                        try: dst.close()
                        except: pass
                t1 = threading.Thread(target=forward, args=(client_sock, chan), daemon=True)
                t2 = threading.Thread(target=forward, args=(chan, client_sock), daemon=True)
                t1.start(); t2.start()
            except socket.timeout: continue
            except Exception as e:
                if running[0]: print(f"[TUNNEL] error: {e}")
                break
    threading.Thread(target=accept_loop, daemon=True).start()
    return host, server_sock, running


async def rpc_call(ws, msg, timeout=30):
    """Send JSON-RPC request and wait for matching response."""
    await ws.send(json.dumps(msg))
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
        resp = json.loads(raw)
        if "id" in resp and resp["id"] == msg["id"]:
            return resp
        # Print notification
        method = resp.get("method", "?")
        params = resp.get("params", {})
        if method == "warning":
            print(f"  ⚠ {params.get('message', str(params)[:200])}")
        elif method not in ("configWarning", "remoteControl/status/changed",
                             "thread/started", "thread/status/changed"):
            pass  # silently ignore during rpc_call
    raise TimeoutError(f"No response for id={msg['id']}")


async def wait_for_completion(ws, timeout=120):
    """Wait for turn/completed notification and collect all streaming messages."""
    deadline = time.monotonic() + timeout
    reasoning_parts = []
    message_parts = []
    final_usage = None
    turn_state = "unknown"

    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
        msg = json.loads(raw)
        method = msg.get("method", "")
        params = msg.get("params", {})

        if method == "item/reasoning/textDelta":
            text = params.get("textDelta", "")
            if text:
                reasoning_parts.append(text)

        elif method == "item/agentMessage/delta":
            text = params.get("textDelta", "")
            if text:
                message_parts.append(text)

        elif method == "turn/completed":
            ts = params.get("status", {})
            turn = params.get("turn", {})
            if isinstance(ts, dict):
                turn_state = ts.get("state", str(ts))
                final_usage = ts.get("usage")
            else:
                turn_state = str(ts)

            # Extract text from turn items in the completed notification
            for item in turn.get("items", []):
                if item.get("type") == "agentMessage":
                    text_val = item.get("text", "")
                    if text_val:
                        message_parts.append(text_val)
                elif item.get("type") == "reasoning":
                    for summary in item.get("summary", []):
                        if isinstance(summary, str):
                            reasoning_parts.append(summary)
                        elif isinstance(summary, dict):
                            reasoning_parts.append(summary.get("text", str(summary)))
            break

        elif method == "turn/items":
            pass  # items come embedded in turn/completed

        elif method in ("thread/status/changed", "thread/tokenUsage/updated",
                        "account/rateLimits/updated", "turn/started", "turn/userPrompt",
                        "turn/settings/update", "model/save", "server/diagnostics",
                        "thread/closed", "item/started", "item/completed"):
            pass

        elif method == "warning":
            print(f"  ⚠ {params.get('message', str(params)[:200])}")

        elif method == "server/diagnostics":
            pass

        elif msg.get("id") is not None:
            pass  # response to a request we already handled

        else:
            print(f"  >>> UNKNOWN: {json.dumps(msg, ensure_ascii=False)[:300]}")

    reasoning_text = "".join(reasoning_parts)
    message_text = "".join(message_parts)
    return turn_state, message_text, reasoning_text, final_usage


async def test_poc(port=18765, token="codex-poc-token-2024"):
    import websockets

    url = f"ws://127.0.0.1:{port}"
    print(f"\n{'='*60}")
    print(f"  Codex PoC: DashScope/Qwen via SSH Tunnel")
    print(f"{'='*60}\n")

    async with websockets.connect(
        url, additional_headers={"Authorization": f"Bearer {token}"}, open_timeout=15,
    ) as ws:
        # Step 1: Initialize
        resp = await rpc_call(ws, {
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": 1, "clientInfo": {"name": "poc-sdk", "version": "0.1"}}
        }, timeout=15)
        result = resp.get("result", {})
        print(f"✓ Initialize OK")

        # Step 2: Start thread
        resp = await rpc_call(ws, {
            "jsonrpc": "2.0", "id": 2, "method": "thread/start", "params": {}
        }, timeout=15)
        thread = resp["result"]["thread"]
        thread_id = thread["id"]
        model = thread.get("model", "?")
        provider = thread.get("modelProvider", "?")
        print(f"✓ Thread started: {model} ({provider})")

        # Step 3: Start turn
        prompt = "用中文回复。请告诉我你是什么AI模型，并写一首关于编程的五言绝句。"
        print(f"\n💬 Prompt: {prompt}\n")

        resp = await rpc_call(ws, {
            "jsonrpc": "2.0", "id": 3, "method": "turn/start",
            "params": {
                "threadId": thread_id,
                "input": [{"type": "text", "text": prompt}]
            }
        }, timeout=30)
        turn = resp.get("result", {}).get("turn", {})
        turn_id = turn.get("id", "?")
        print(f"✓ Turn started: {turn_id[:30]}...")

        # Step 4: Wait for completion
        print(f"  Waiting for model response...")
        state, text, reasoning, usage = await wait_for_completion(ws, timeout=120)

        print(f"\n{'='*60}")
        if text:
            print(f"  🤖 MODEL RESPONSE:")
            print(f"  {'-'*56}")
            for line in text.split('\n'):
                print(f"  {line}")
            print(f"  {'-'*56}")
        if reasoning:
            print(f"\n  💭 Reasoning summary: {reasoning[:500]}")
        if usage:
            print(f"\n  📊 Tokens: {json.dumps(usage, ensure_ascii=False)}")
        if not text:
            print(f"  ⚠ No text captured (state={state})")
        print(f"{'='*60}")

        await ws.close()
        return thread_id


async def main():
    port = 18765
    host, server_sock, running = create_tunnel(port)
    try:
        await asyncio.sleep(0.5)
        await test_poc(port)
    finally:
        running[0] = False
        try: server_sock.close()
        except: pass
        host.close()

if __name__ == "__main__":
    asyncio.run(main())