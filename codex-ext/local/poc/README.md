# Codex PoC — Python SDK + App Server + Codex Harness → DashScope/Qwen

## Overview

This PoC demonstrates the full Codex end-to-end pipeline using **locally built source code**,
connecting to Alibaba Cloud's DashScope API with the Qwen3.7-plus model:

```
┌──────────────┐    JSON-RPC (stdio)    ┌─────────────┐    HTTP/SSE    ┌───────────────┐
│  Python SDK  │ ◄────────────────────► │  app-server  │ ◄───────────► │  DashScope API │
│ (poc_demo.py)│                        │  (codex bin) │               │  (Qwen model)  │
└──────────────┘                        └──────┬───────┘               └───────────────┘
                                               │
                                               │ exec-server-protocol
                                        ┌──────▼───────┐
                                        │  exec-server  │
                                        │ (sandboxed)   │
                                        └──────────────┘
```

- **Python SDK** launches `codex app-server --listen stdio://` as a subprocess
- **app-server** reads `config.toml` for the DashScope model_provider, calls the model API
- **exec-server** handles sandboxed command execution (auto-managed by app-server)
- **Authentication** uses `env_key`-based Bearer token (no `login_api_key` needed)

### Key: How Auth Works

Custom providers with `requires_openai_auth = false` skip the OpenAI login flow entirely.
The API key is read from the `DASHSCOPE_API_KEY` environment variable at request time
via the provider's `env_key` config. No `codex.login_api_key()` call is needed.

> **⚠️ Wire API Note:** Codex v0.155.1 only supports `wire_api = "responses"` (OpenAI's
> `POST /v1/responses` endpoint). DashScope's compatible-mode endpoint traditionally
> only supports `/v1/chat/completions`. If you get a 404 error, you may need the
> `codex-responses-api-proxy` binary as a bridge, or a translation proxy like LiteLLM.

## Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Rust | 1.95+ (stable) | `rustup` |
| Python | 3.10+ | `python.org` or `winget` |
| uv (optional) | latest | `pip install uv` |

## Quick Start

### 1. Set API Key

Create a `.env` file from the template:

```powershell
copy .env.example .env
# Edit .env with your DashScope API key:
# DASHSCOPE_API_KEY=sk-your-key-here
```

Or set it directly:

```powershell
$env:DASHSCOPE_API_KEY = "sk-e4586ec037624d6792b1c7a4a850cef2"
```

### 2. Build & Run

```powershell
.\run.ps1
```

This will:
1. Check prerequisites (Rust, Python, pydantic)
2. Build the `codex` binary from source (first time takes ~5-15 min)
3. Install Python SDK dependencies
4. Run the PoC demo connecting to DashScope/Qwen

### 3. Expected Output

```
=== Codex PoC Demo ===
Python SDK + App Server + Codex Harness → DashScope/Qwen

Binary:    .../codex.exe
SDK src:   .../sdk/python/src
PoC root:  .../PoC
--------------------------------------------------
Model:     qwen3.7-plus
Provider:  dashscope (via .../.codex-poc-home/config.toml)
[1/4] Starting Codex client (launching app-server over stdio)...
  Server: Codex 0.155.1
[2/4] Auth via DASHSCOPE_API_KEY env var (no login needed)...
  Auth OK (env_key-based, Bearer token)
[3/4] Creating thread and running prompt: 'Say hello in one sentence...'
  Thread ID: thread_abc123
  Turn ID:   turn_xyz789
  Status:    completed
  Duration:  2.3s
[4/4] Response:
  Hello! I'm Qwen, a large language model created by Alibaba Cloud.
----------------------------------------
==================================================
PoC completed successfully!
```

## Generated Config

The PoC auto-generates `config.toml` in the isolated CODEX_HOME:

```toml
model = "qwen3.7-plus"
model_provider = "dashscope"
approval_policy = "never"
sandbox_mode = "read-only"

[model_providers.dashscope]
name = "DashScope (Qwen)"
base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
env_key = "DASHSCOPE_API_KEY"
wire_api = "responses"
requires_openai_auth = false
```

## Manual Steps

### Build only

```powershell
.\build.ps1
```

### Run only (skip build)

```powershell
.\run.ps1 -SkipBuild
```

### Run with custom model

```powershell
$env:CODEX_MODEL = "qwen3.7-plus"
.\run.ps1
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DASHSCOPE_API_KEY` | Yes | DashScope API key for Qwen models |
| `CODEX_MODEL` | No | Model name (default: qwen3.7-plus) |
| `CODEX_DASHSCOPE_URL` | No | DashScope API URL (default: dashscope.aliyuncs.com/compatible-mode/v1) |
| `CODEX_HOME` | No | Codex home directory (default: .codex-poc-home in PoC dir) |
| `CODEX_LOG` | No | Log level (default: info) |
| `CODEX_MODEL_CONTEXT_WINDOW` | No | Model context window in tokens (default: 131072) |

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `cargo: command not found` | Install Rust: https://rustup.rs |
| `pydantic not found` | Run: `pip install pydantic pydantic-core` |
| Build takes too long | First build is slow; subsequent builds use cached artifacts |
| `Binary not found` | Run `.\build.ps1` first |
| `404 Not Found` on /v1/responses | DashScope may not support Responses API. Use the `codex-responses-api-proxy` or LiteLLM as a bridge |
| `401 Unauthorized` | Check your `DASHSCOPE_API_KEY` |
| `EnvVar(DASHSCOPE_API_KEY)` | Make sure DASHSCOPE_API_KEY is set in .env or environment |
| `ConnectError` | Ensure no other codex process is using the same port |
| Responses API format mismatch | If you see errors about response format, DashScope's compatible mode may not support OpenAI's Responses API — consider using a translation proxy |

## Wire API Compatibility

Codex v0.155.1 removed support for `wire_api = "chat"` and only supports
`wire_api = "responses"` (OpenAI's `POST /v1/responses` endpoint).

If DashScope's compatible-mode endpoint doesn't support `/v1/responses`:
- The built-in `codex-responses-api-proxy` binary can forward requests (but expects Responses API upstream)
- Third-party proxies like [LiteLLM](https://github.com/BerriAI/litellm),
  [one-api](https://github.com/songquanpeng/one-api), or a custom Python Flask proxy
  can translate between Responses API and Chat Completions API formats