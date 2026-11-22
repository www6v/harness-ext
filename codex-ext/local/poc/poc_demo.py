#!/usr/bin/env python3
"""Codex PoC Demo — Python SDK + App Server + Codex Harness (DashScope/Qwen).

This script demonstrates the full Codex pipeline using a locally built binary:
  1. Launches codex app-server over stdio (via the Python SDK)
  2. Configures a custom model_provider for DashScope's Qwen model
  3. Creates a thread, runs a turn with a simple prompt
  4. Prints the model response and turn results

Prerequisites:
  - codex binary built from source (run build.ps1 first)
  - DASHSCOPE_API_KEY environment variable set (or .env file with credentials)
  - Python 3.10+ with pydantic installed
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path


def _resolve_paths() -> tuple[Path, Path, Path]:
    """Resolve the three key paths: PoC root, SDK source, and codex binary."""
    poc_root = Path(os.environ.get("CODEX_POC_ROOT", Path(__file__).resolve().parent))

    # SDK source: <repo>/sdk/python/src
    sdk_src = poc_root.parent.parent / "codex-rust-v0.155.1" / "sdk" / "python" / "src"
    if not sdk_src.exists():
        for ancestor in Path(__file__).resolve().parents:
            candidate = ancestor / "sdk" / "python" / "src"
            if candidate.exists():
                sdk_src = candidate
                break
        else:
            raise FileNotFoundError(
                "Cannot locate SDK source at sdk/python/src. "
                "Set CODEX_POC_ROOT or run from the PoC directory."
            )
    sdk_src = sdk_src.resolve()

    # Codex binary: <repo>/codex-rs/target/debug/codex[.exe]
    codex_rs = poc_root.parent.parent / "codex-rust-v0.155.1" / "codex-rs"
    codex_name = "codex.exe" if sys.platform == "win32" else "codex"
    codex_bin = codex_rs / "target" / "debug" / codex_name
    if not codex_bin.exists():
        codex_bin = codex_rs / "target" / "release" / codex_name
    if not codex_bin.exists():
        raise FileNotFoundError(
            f"Codex binary not found at {codex_bin}.\n"
            "Run build.ps1 first to build from source."
        )
    codex_bin = codex_bin.resolve()

    return poc_root, sdk_src, codex_bin


def _setup_python_path(sdk_src: Path) -> None:
    """Add SDK source to sys.path so openai_codex can be imported directly."""
    sdk_src_str = str(sdk_src)
    if sdk_src_str not in sys.path:
        sys.path.insert(0, sdk_src_str)


def _check_dependencies() -> None:
    """Verify required Python packages are available."""
    try:
        import pydantic  # noqa: F401
    except ImportError as exc:
        raise ImportError(
            "pydantic is required. Install with: pip install pydantic"
        ) from exc


def _get_api_key() -> str:
    """Get DashScope API key from environment or prompt the user."""
    key = os.environ.get("DASHSCOPE_API_KEY")
    if key:
        return key

    # Fallback: check OPENAI_API_KEY (for backward compat)
    key = os.environ.get("OPENAI_API_KEY")
    if key:
        print("Warning: Using OPENAI_API_KEY. Prefer DASHSCOPE_API_KEY instead.")
        return key

    print("No DASHSCOPE_API_KEY found in environment.")
    print("Enter your DashScope API key:")
    try:
        import getpass
        key = getpass.getpass("API Key: ")
    except Exception:
        key = input("API Key: ").strip()
    if not key:
        raise ValueError("API key is required to run the PoC.")
    return key


def _setup_codex_home(poc_root: Path, api_key: str) -> Path:
    """Create an isolated CODEX_HOME directory for the PoC.

    Writes a config.toml with a DashScope model_provider configured for
    Qwen3.7-plus via the DashScope OpenAI-compatible API.
    """
    codex_home = os.environ.get("CODEX_HOME")
    if codex_home:
        return Path(codex_home).resolve()

    home = poc_root / ".codex-poc-home"
    home.mkdir(parents=True, exist_ok=True)

    dashscope_url = os.environ.get(
        "CODEX_DASHSCOPE_URL",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    config_toml = home / "config.toml"

    # Write the DashScope provider config
    # NOTE: Codex v0.155.1 only supports wire_api="responses" (OpenAI Responses API).
    # If DashScope doesn't support /v1/responses, a proxy is needed.
    # The responses-api-proxy (codex-responses-api-proxy binary) can bridge this.
    config_toml.write_text(
        f"""\
# PoC config -- auto-generated for DashScope/Qwen
model = "qwen3.7-plus"
model_provider = "dashscope"
approval_policy = "never"
sandbox_mode = "read-only"

[model_providers.dashscope]
name = "DashScope (Qwen)"
base_url = "{dashscope_url}"
env_key = "DASHSCOPE_API_KEY"
wire_api = "responses"
requires_openai_auth = false

"""
    )
    return home


def main() -> int:
    """Run the PoC demo."""
    print("=== Codex PoC Demo ===")
    print("Python SDK + App Server + Codex Harness → DashScope/Qwen")
    print()

    # Resolve paths
    try:
        poc_root, sdk_src, codex_bin = _resolve_paths()
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Binary:    {codex_bin}")
    print(f"SDK src:   {sdk_src}")
    print(f"PoC root:  {poc_root}")
    print("-" * 50)

    # Setup
    _setup_python_path(sdk_src)
    _check_dependencies()
    api_key = _get_api_key()
    codex_home = _setup_codex_home(poc_root, api_key)

    # Import SDK (must be after path setup)
    from openai_codex import Codex, CodexConfig

    # Resolve model from env or use Qwen default
    model = os.environ.get("CODEX_MODEL", "qwen3.7-plus")

    # Environment variables for the app-server subprocess
    extra_env = {
        "CODEX_HOME": str(codex_home),
        "DASHSCOPE_API_KEY": api_key,
    }
    if os.environ.get("CODEX_LOG"):
        extra_env["RUST_LOG"] = os.environ["CODEX_LOG"]

    print()
    print(f"Model:     {model}")
    print(f"Provider:  dashscope (via {extra_env['CODEX_HOME']}/config.toml)")
    print(f"[1/4] Starting Codex client (launching app-server over stdio)...")

    config = CodexConfig(
        codex_bin=str(codex_bin),
        cwd=str(poc_root),
        env=extra_env,
    )

    try:
        with Codex(config=config) as codex:
            metadata = codex.metadata
            print(f"  Server: {metadata.serverInfo.name} {metadata.serverInfo.version}")

            # Step 2: No login_api_key needed for custom providers with
            # requires_openai_auth=false. The API key is read from the
            # DASHSCOPE_API_KEY env var via the provider's env_key config.
            print(f"[2/4] Auth via DASHSCOPE_API_KEY env var (no login needed)...")
            print("  Auth OK (env_key-based, Bearer token)")

            # Step 3: Create thread and run turn
            prompt = "Say hello in one sentence, and tell me what model you are."
            print(f"[3/4] Creating thread and running prompt: '{prompt}'")

            thread = codex.thread_start(
                model=model,
                base_instructions=(
                    "You are a helpful assistant. Keep responses concise."
                ),
            )

            t0 = time.monotonic()
            result = thread.run(prompt)
            elapsed = time.monotonic() - t0

            print(f"  Thread ID: {thread.id}")
            print(f"  Turn ID:   {result.id}")
            print(
                f"  Status:    {result.status.value if hasattr(result.status, 'value') else result.status}"
            )
            print(f"  Duration:  {elapsed:.1f}s")
            if result.usage:
                print(
                    f"  Tokens:    {result.usage.input_tokens if hasattr(result.usage, 'input_tokens') else 'N/A'} in / "
                    f"{result.usage.output_tokens if hasattr(result.usage, 'output_tokens') else 'N/A'} out"
                )
            print(f"  Items:     {len(result.items)} response items")

            # Step 4: Display response
            print()
            print("[4/4] Response:")
            print("-" * 40)
            if result.final_response:
                print(result.final_response)
            else:
                print("(empty response)")
            print("-" * 40)

            if result.error:
                print(f"  Turn error: {result.error}")

    except Exception as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()

        # Provide helpful context for common errors
        if "EnvVar" in str(exc) or "DASHSCOPE_API_KEY" in str(exc):
            print("\nHint: Set DASHSCOPE_API_KEY environment variable.")
        if "Connection" in str(exc) or "refused" in str(exc).lower():
            print("\nHint: Ensure no other codex process is running.")
        if "404" in str(exc) or "Not Found" in str(exc):
            print(
                "\nHint: DashScope may not support /v1/responses endpoint. "
                "Consider using codex-responses-api-proxy as a bridge."
            )
        return 1

    print()
    print("=" * 50)
    print("PoC completed successfully!")
    return 0


if __name__ == "__main__":
    sys.exit(main())