# =============================================================================
# DeepSeek Harness - Multi-stage Docker Build
# =============================================================================
# This Dockerfile builds the DeepSeek Harness application in a multi-stage
# process to minimize the final image size.
# =============================================================================

# ----------------------------------------------------------------------------
# Stage 1: Base image with Node.js
# ----------------------------------------------------------------------------
FROM node:22-alpine AS base

# Install pnpm
RUN corepack enable && corepack prepare pnpm@11.7.0 --activate

# Set working directory
WORKDIR /app

# Install build dependencies for native modules
RUN apk add --no-cache \
    python3 \
    make \
    g++ \
    git \
    bash

# ----------------------------------------------------------------------------
# Stage 2: Dependencies installation
# ----------------------------------------------------------------------------
FROM base AS deps

# Copy package files
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./

# Copy all package.json files from workspaces to optimize layer caching
COPY apps/cli/package.json ./apps/cli/
COPY packages/ ./packages/
COPY vendor/ ./vendor/
COPY native/ ./native/

# Install dependencies
RUN pnpm install --frozen-lockfile

# ----------------------------------------------------------------------------
# Stage 3: Build the application
# ----------------------------------------------------------------------------
FROM deps AS builder

# Copy source code
COPY . .

# Build the application
RUN pnpm run build

# Build native system components
RUN pnpm run build:native-system

# ----------------------------------------------------------------------------
# Stage 4: Production image
# ----------------------------------------------------------------------------
FROM node:22-alpine AS production

# Install pnpm
RUN corepack enable && corepack prepare pnpm@11.7.0 --activate

# Set working directory
WORKDIR /app

# Install dumb-init for proper signal handling
RUN apk add --no-cache dumb-init

# Create non-root user
RUN addgroup -g 1001 -S nodejs && \
    adduser -S nodejs -u 1001

# Copy built artifacts from builder
COPY --from=builder --chown=nodejs:nodejs /app/node_modules ./node_modules
COPY --from=builder --chown=nodejs:nodejs /app/apps/cli/lib ./apps/cli/lib
COPY --from=builder --chown=nodejs:nodejs /app/apps/cli/package.json ./apps/cli/
COPY --from=builder --chown=nodejs:nodejs /app/packages ./packages
COPY --from=builder --chown=nodejs:nodejs /app/vendor ./vendor
COPY --from=builder --chown=nodejs:nodejs /app/native ./native
COPY --from=builder --chown=nodejs:nodejs /app/package.json ./
COPY --from=builder --chown=nodejs:nodejs /app/pnpm-workspace.yaml ./
COPY --from=builder --chown=nodejs:nodejs /app/pnpm-lock.yaml ./

# Copy configuration files
COPY --from=builder --chown=nodejs:nodejs /app/tsconfig*.json ./
COPY --from=builder --chown=nodejs:nodejs /app/scripts ./scripts

# Switch to non-root user
USER nodejs

# Expose port (if web server is enabled)
EXPOSE 3000

# Set environment variables
ENV NODE_ENV=production
ENV DSH_HOME=/app/.dsh

# Use dumb-init as entrypoint for proper signal handling
ENTRYPOINT ["dumb-init", "--"]

# Default command
CMD ["node", "--import", "tsx/esm", "apps/cli/src/bin.ts", "--help"]

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD node -e "console.log('healthy')" || exit 1

# Labels
LABEL org.opencontainers.image.title="DeepSeek Harness"
LABEL org.opencontainers.image.description="DeepSeek Harness - AI Agent Harness"
LABEL org.opencontainers.image.vendor="DeepSeek AI"
LABEL org.opencontainers.image.source="https://github.com/deepseek-ai/deepseek-harness"
