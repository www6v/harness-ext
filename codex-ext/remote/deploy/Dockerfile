# Codex App-Server Container
# Build context: /data/disk/codex-build (contains codex binary and config)
# docker build -t codex-server:latest -f deploy/Dockerfile /data/disk/codex-build

FROM ubuntu:24.04

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    bubblewrap \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash codex

# Copy the pre-built codex binary
COPY codex-rs/target/release/codex /usr/local/bin/codex
RUN chmod +x /usr/local/bin/codex

# Setup codex home with config
RUN mkdir -p /home/codex/.codex && chown -R codex:codex /home/codex
COPY config.toml /home/codex/.codex/config.toml
RUN chown codex:codex /home/codex/.codex/config.toml

# WebSocket auth token (capability-token mode)
RUN echo "codex-poc-token-2024" > /home/codex/.codex/ws-token && \
    chown codex:codex /home/codex/.codex/ws-token && \
    chmod 600 /home/codex/.codex/ws-token

USER codex
WORKDIR /home/codex
EXPOSE 8765

ENV CODEX_HOME=/home/codex/.codex

ENTRYPOINT ["codex"]
CMD ["app-server", "--listen", "ws://0.0.0.0:8765", "--ws-auth", "capability-token", "--ws-token-file", "/home/codex/.codex/ws-token"]