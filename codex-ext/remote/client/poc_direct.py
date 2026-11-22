"""PoC: Direct remote access to codex app-server (no SSH tunnel needed).
Usage: python _poc_remote.py

Flow: initialize -> thread/start -> turn/start -> wait for turn/completed
"""
import asyncio, json, time

HOST = "124.221.28.203"
PORT = 8765
TOKEN = "codex-poc-token-2024"


async def rpc_call(ws, msg, timeout=30):
    """Send JSON-RPC request and wait for matching response, printing warnings."""
    await ws.send(json.dumps(msg))
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
        resp = json.loads(raw)
        if "id" in resp and resp["id"] == msg["id"]:
            return resp
        method = resp.get("method", "?")
        params = resp.get("params", {})
        if method == "warning":
            print(f"  ⚠ {params.get('message', str(params)[:200])}")
    raise TimeoutError(f"No response for id={msg['id']}")


async def wait_for_completion(ws, timeout=120):
    """Wait for turn/completed and collect assistant text + reasoning."""
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
            # Extract from turn items
            for item in turn.get("items", []):
                if item.get("type") == "agentMessage":
                    t = item.get("text", "")
                    if t:
                        message_parts.append(t)
                elif item.get("type") == "reasoning":
                    for s in item.get("summary", []):
                        if isinstance(s, str):
                            reasoning_parts.append(s)
            break

    return turn_state, "".join(message_parts), "".join(reasoning_parts), final_usage


async def main():
    import websockets

    url = f"ws://{HOST}:{PORT}"
    print(f"{'='*60}")
    print(f"  Codex PoC: Direct Remote Access")
    print(f"  {url}")
    print(f"{'='*60}\n")

    try:
        async with websockets.connect(
            url,
            additional_headers={"Authorization": f"Bearer {TOKEN}"},
            open_timeout=10,
        ) as ws:
            # 1. Initialize
            resp = await rpc_call(ws, {
                "jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {"protocolVersion": 1, "clientInfo": {"name": "poc-remote", "version": "0.1"}}
            }, timeout=10)
            print(f"✓ Connected to codex app-server")
            print(f"  Home: {resp['result'].get('codexHome')}")

            # 2. Start thread
            resp = await rpc_call(ws, {
                "jsonrpc": "2.0", "id": 2, "method": "thread/start", "params": {}
            }, timeout=15)
            thread = resp["result"]["thread"]
            thread_id = thread["id"]
            model = thread.get("model", "?")
            provider = thread.get("modelProvider", "?")
            print(f"✓ Thread: {model} ({provider})")

            # 3. Start turn
            prompt = "用中文回复。请告诉我你是什么AI模型，并写一首关于编程的五言绝句。"
            print(f"\n💬 {prompt}\n")

            resp = await rpc_call(ws, {
                "jsonrpc": "2.0", "id": 3, "method": "turn/start",
                "params": {
                    "threadId": thread_id,
                    "input": [{"type": "text", "text": prompt}]
                }
            }, timeout=30)
            print(f"✓ Turn started, waiting for model...")

            # 4. Wait for completion
            state, text, reasoning, usage = await wait_for_completion(ws, timeout=120)

            print(f"\n{'='*60}")
            if text:
                print(f"  🤖 RESPONSE:")
                print(f"  {'-'*56}")
                for line in text.split('\n'):
                    print(f"  {line}")
                print(f"  {'-'*56}")
            if usage:
                print(f"\n  📊 {json.dumps(usage, ensure_ascii=False)}")
            print(f"{'='*60}")

    except TimeoutError:
        print("\n❌ Connection timed out - is port 8765 open?")
    except Exception as e:
        print(f"\n❌ Error: {e}")


if __name__ == "__main__":
    asyncio.run(main())