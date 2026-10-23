#!/bin/bash
# =============================================================================
# Quick Remote Deployment Commands
# =============================================================================
# Copy and paste these commands into your SSH session
# =============================================================================

# SSH into the server:
# ssh root@111.229.26.170
# Password: 1qaZxsw@

# Then run these commands:

cd /home/wei/deepseek-harness-ext/deploy

# Make scripts executable
chmod +x *.sh

# Enable Docker BuildKit for faster builds
export DOCKER_BUILDKIT=1
export COMPOSE_DOCKER_CLI_BUILD=1

# Build the image (with progress output)
echo "Building Docker image..."
docker compose build --progress=plain

# Start the containers
echo "Starting containers..."
docker compose up -d

# Check status
echo "Container status:"
docker compose ps

# View logs
echo "Recent logs:"
docker compose logs --tail=50

echo "Deployment complete!"
