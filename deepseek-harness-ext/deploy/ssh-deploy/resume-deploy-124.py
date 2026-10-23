#!/usr/bin/env python3
"""Deploy to 124.221.28.203 - v3: truly background build"""
import paramiko, sys, time

HOST = '124.221.28.203'
USER = 'root'
PASS = '1qaZxsw@'
EXT_DIR = '/home/ubuntu/wei/deepseek-harness-ext/deploy'

def run(client, cmd, timeout=30):
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    code = stdout.channel.recv_exit_status()
    return code, out, err

def fire_and_forget(client, cmd):
    """Run command in background without waiting for output"""
    transport = client.get_transport()
    channel = transport.open_session()
    channel.exec_command(cmd)
    time.sleep(1)  # give it a moment to start
    return channel

def connect():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(hostname=HOST, username=USER, password=PASS, timeout=30, banner_timeout=30)
    return client

client = connect()
print('Connected!\n')

# Step 1: Upload optimized Dockerfile with China mirrors for install stage
print('=== Step 1: Upload optimized Dockerfile ===')
dockerfile_content = r'''# =============================================================================
# DeepSeek Harness - Dockerfile for Production (China Optimized)
# =============================================================================

# syntax=docker/dockerfile:1

# ----------------------------------------------------------------------------
# Stage 1: Install - resolve all pnpm workspace dependencies
# ----------------------------------------------------------------------------
FROM node:22-bookworm-slim AS install
ARG NPM_REGISTRY=https://registry.npmmirror.com
ARG APT_MIRROR=mirrors.aliyun.com

# Replace Debian mirrors with China mirror for faster downloads
RUN sed -i "s|deb.debian.org|${APT_MIRROR}|g; s|security.debian.org|${APT_MIRROR}|g" \
      /etc/apt/sources.list.d/debian.sources \
  && corepack enable && corepack prepare pnpm@11.7.0 --activate \
  && apt-get update \
  && apt-get install -y --no-install-recommends build-essential python3 \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /src

# Copy manifests first for layer caching
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
COPY patches/ ./patches/

RUN pnpm config set registry "${NPM_REGISTRY}" \
  && pnpm install --registry "${NPM_REGISTRY}" --frozen-lockfile --ignore-scripts

# ----------------------------------------------------------------------------
# Stage 2: Build - TypeScript compile + Vite web bundle
# ----------------------------------------------------------------------------
FROM install AS build

COPY . .

# Build TypeScript host packages, client packages, then web frontend
RUN pnpm run build:lib:host \
  && pnpm run build:lib:client \
  && pnpm run build:web \
  && pnpm run build:native-system

# ----------------------------------------------------------------------------
# Stage 2b: Runtime-prep - run postinstall scripts so node_modules
# is complete (native binaries, etc.) before runtime.
# ----------------------------------------------------------------------------
FROM build AS runtime-prep

RUN printf 'registry=https://registry.npmmirror.com\n' > .npmrc
RUN pnpm install --frozen-lockfile

# ----------------------------------------------------------------------------
# Stage 3: Runtime - minimal Node with compiled monorepo
# ----------------------------------------------------------------------------
FROM node:22-bookworm-slim AS runtime

ARG APT_MIRROR=mirrors.aliyun.com

RUN sed -i "s|deb.debian.org|${APT_MIRROR}|g; s|security.debian.org|${APT_MIRROR}|g" \
      /etc/apt/sources.list.d/debian.sources \
  && apt-get update \
  && apt-get install -y --no-install-recommends ca-certificates curl \
  && rm -rf /var/lib/apt/lists/* \
  && corepack enable && corepack prepare pnpm@11.7.0 --activate

WORKDIR /app

COPY --from=runtime-prep /src/package.json /src/pnpm-workspace.yaml /src/pnpm-lock.yaml /src/.npmrc ./
COPY --from=runtime-prep /src/patches/ ./patches/
COPY --from=runtime-prep /src/node_modules/ ./node_modules/

COPY --from=build /src/apps/ ./apps/
COPY --from=build /src/packages/ ./packages/
COPY --from=build /src/vendor/ ./vendor/
COPY --from=build /src/native/ ./native/
COPY --from=build /src/scripts/ ./scripts/

ENV NODE_ENV=production \
    DSH_WEB_PORT=3080 \
    DSH_ALLOW_WILDCARD_HOST=1 \
    DSH_HOME=/app/.dsh

EXPOSE 3080

HEALTHCHECK --interval=5s --timeout=3s --start-period=30s --retries=20 \
  CMD ["curl", "-sf", "http://127.0.0.1:3080/"]

CMD ["node", "apps/cli/lib/bin.js", "web", "--host", "0.0.0.0", "--port", "3080", "--no-open", "--trusted-host", "124.221.28.203"]

LABEL org.opencontainers.image.title="DeepSeek Harness"
LABEL org.opencontainers.image.description="DeepSeek Harness - AI Agent Harness"
LABEL org.opencontainers.image.vendor="DeepSeek AI"
'''

# Write Dockerfile via SSH
run(client, f"cat > {EXT_DIR}/Dockerfile << 'DOCKERFILE_EOF'\n{dockerfile_content}\nDOCKERFILE_EOF")
# Also save as Dockerfile.optimized
run(client, f"cp {EXT_DIR}/Dockerfile {EXT_DIR}/Dockerfile.optimized")
print('Dockerfile uploaded with China mirrors for all stages!')

# Verify
code, out, _ = run(client, f'head -18 {EXT_DIR}/Dockerfile')
print(out)

# Step 2: Cleanup old containers
print('\n=== Step 2: Cleanup ===')
code, out, _ = run(client, f'cd {EXT_DIR} && docker compose down 2>&1')
print(out or 'Nothing to stop')

# Step 3: Start background build
print('\n=== Step 3: Starting background build ===')
build_script = f'''#!/bin/bash
cd {EXT_DIR}
export DOCKER_BUILDKIT=1
export COMPOSE_DOCKER_CLI_BUILD=1
echo "BUILD START: $(date)" > /tmp/build-output.log
docker compose --progress plain build --no-cache dsh >> /tmp/build-output.log 2>&1
if [ $? -eq 0 ]; then
  echo "BUILD_SUCCESS" >> /tmp/build-output.log
else
  echo "BUILD_FAILED" >> /tmp/build-output.log
fi
echo "BUILD END: $(date)" >> /tmp/build-output.log
'''
run(client, f"echo '{build_script}' > /tmp/build.sh && chmod +x /tmp/build.sh")

# Launch in background with nohup
fire_and_forget(client, 'nohup /tmp/build.sh > /dev/null 2>&1 &')
print('Build started in background. Polling for completion...')

# Step 4: Wait for build
print('\n=== Step 4: Waiting for build ===')
for i in range(120):  # max 60 minutes
    time.sleep(30)
    code, out, _ = run(client, 'tail -1 /tmp/build-output.log 2>/dev/null || echo "NO_LOG"')

    if 'BUILD_SUCCESS' in out:
        print(f'\n  *** BUILD SUCCESS after {(i+1)*30}s! ***')
        break
    elif 'BUILD_FAILED' in out:
        print(f'\n  BUILD FAILED after {(i+1)*30}s!')
        code, tail, _ = run(client, 'tail -80 /tmp/build-output.log')
        print(tail)
        client.close()
        sys.exit(1)
    else:
        # Show progress
        code, progress, _ = run(client, 'grep -cE "^#\\d+" /tmp/build-output.log 2>/dev/null || echo "0"')
        code2, last_line, _ = run(client, 'grep -E "DONE|CACHED|\\[" /tmp/build-output.log 2>/dev/null | tail -1')
        lines = progress.strip()
        last = last_line.strip()[:100] if last_line else 'building...'
        print(f'  {(i+1)*30}s: {lines} steps done | {last}')
else:
    print('BUILD TIMEOUT after 60 minutes!')
    code, out, _ = run(client, 'tail -30 /tmp/build-output.log')
    print(out)
    client.close()
    sys.exit(1)

# Step 5: Verify image
print('\n=== Step 5: Verify image ===')
code, out, _ = run(client, 'docker images deploy-dsh --format "{{.Tag}} {{.Size}} {{.CreatedAt}}"')
print(f'deploy-dsh: {out}')

# Step 6: Start container
print('\n=== Step 6: Start container ===')
code, out, _ = run(client, f'cd {EXT_DIR} && docker compose up -d dsh 2>&1')
print(out)

# Step 7: Wait for healthy
print('\n=== Step 7: Wait for healthy ===')
for i in range(18):
    time.sleep(10)
    code, out, _ = run(client, f'cd {EXT_DIR} && docker compose ps --format "{{{{.Status}}}}" 2>&1')
    if 'healthy' in out:
        print(f'  Container healthy after {(i+1)*10}s!')
        break
    print(f'  {(i+1)*10}s: {out}')
else:
    print('  Not yet healthy after 180s, checking logs...')

# Step 8: Final verification
print('\n' + '='*60)
print('FINAL STATUS')
print('='*60)
code, out, _ = run(client, f'cd {EXT_DIR} && docker compose ps 2>&1')
print(out)

code, out, _ = run(client, f'cd {EXT_DIR} && docker compose logs dsh --tail=5 2>&1')
print(f'\nLogs:\n{out}')

code, token_line, _ = run(client, f'cd {EXT_DIR} && docker compose logs dsh 2>&1 | grep -oP "token=[A-Za-z0-9_-]+" | head -1')
if token_line:
    print(f'\n*** Access URL: http://124.221.28.203:3080/?{token_line} ***')

# API tests
print('\n=== API tests ===')
code, out, _ = run(client, 'curl -sf -o /dev/null -w "%{http_code}" -H "Host: 124.221.28.203:3080" http://127.0.0.1:3080/')
print(f'Web page: HTTP {out}')

code, out, _ = run(client, 'curl -sf -o /dev/null -w "%{http_code}" -H "Host: 124.221.28.203:3080" -H "Content-Type: application/json" -X POST -d \'{"method":"settings/describe","payload":{"args":{}}}\' http://127.0.0.1:3080/api/settings/describe')
print(f'Settings API: HTTP {out}')

code, out, _ = run(client, 'curl -sf -o /dev/null -w "%{http_code}" -H "Host: 124.221.28.203:3080" http://127.0.0.1:3080/api/llm/listProviders')
print(f'listProviders API: HTTP {out}')

client.close()
print('\n=== Deployment complete! ===')
