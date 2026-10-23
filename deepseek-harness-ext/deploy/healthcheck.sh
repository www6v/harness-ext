#!/bin/bash
# =============================================================================
# DeepSeek Harness - Docker Health Check Script
# =============================================================================
# This script performs health checks on the DeepSeek Harness Docker deployment
# =============================================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")/deepseek-harness"

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[✓]${NC} $1"
}

log_error() {
    echo -e "${RED}[✗]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

echo ""
echo "====================================="
echo "DeepSeek Harness Health Check"
echo "====================================="
echo ""

# Check Docker
log_info "Checking Docker..."
if docker info > /dev/null 2>&1; then
    log_success "Docker is running"
else
    log_error "Docker is not running"
    exit 1
fi

# Check docker compose
log_info "Checking docker compose..."
if docker compose version &> /dev/null; then
    log_success "docker compose is available"
else
    log_error "docker compose is not installed"
    exit 1
fi

# Check containers
log_info "Checking containers..."
cd "$PROJECT_DIR"

CONTAINERS=$(docker compose -f "$SCRIPT_DIR/docker-compose.yml" ps -q)

if [ -z "$CONTAINERS" ]; then
    log_warning "No containers are running"
    echo ""
    echo "Start containers with:"
    echo "  ./deploy.sh up"
    exit 0
fi

# Check each container
for container in $CONTAINERS; do
    CONTAINER_NAME=$(docker inspect --format='{{.Name}}' "$container" | sed 's/\///')
    CONTAINER_STATUS=$(docker inspect --format='{{.State.Status}}' "$container")
    CONTAINER_HEALTH=$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}no-healthcheck{{end}}' "$container")

    if [ "$CONTAINER_STATUS" == "running" ]; then
        if [ "$CONTAINER_HEALTH" == "healthy" ]; then
            log_success "$CONTAINER_NAME is running and healthy"
        elif [ "$CONTAINER_HEALTH" == "no-healthcheck" ]; then
            log_success "$CONTAINER_NAME is running (no healthcheck)"
        else
            log_warning "$CONTAINER_NAME is running but health status: $CONTAINER_HEALTH"
        fi
    else
        log_error "$CONTAINER_NAME is not running (status: $CONTAINER_STATUS)"
    fi
done

# Check API connectivity (if DEEPSEEK_API_KEY is set)
echo ""
log_info "Checking API configuration..."
if [ -n "$DEEPSEEK_API_KEY" ]; then
    log_success "DEEPSEEK_API_KEY is configured"
else
    log_warning "DEEPSEEK_API_KEY is not set"
    echo "  Set it with: export DEEPSEEK_API_KEY=your-key"
fi

# Check volumes
echo ""
log_info "Checking volumes..."
VOLUMES=$(docker volume ls -q | grep deepseek-harness)
if [ -n "$VOLUMES" ]; then
    log_success "Volumes exist:"
    echo "$VOLUMES" | sed 's/^/    /'
else
    log_warning "No volumes found (will be created on first run)"
fi

# Check disk space
echo ""
log_info "Checking disk space..."
DOCKER_DISK=$(docker system df --format '{{.Size}}' | head -1)
log_success "Docker disk usage: $DOCKER_DISK"

echo ""
echo "====================================="
echo "Health check completed!"
echo "====================================="
echo ""
