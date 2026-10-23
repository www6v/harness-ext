#!/bin/bash
# =============================================================================
# DeepSeek Harness - Docker Update Script
# =============================================================================
# This script updates the DeepSeek Harness Docker deployment
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
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

echo ""
echo "====================================="
echo "DeepSeek Harness Update"
echo "====================================="
echo ""

cd "$PROJECT_DIR"

# Backup before update
log_info "Creating backup before update..."
"$SCRIPT_DIR/backup.sh" "./backups" || {
    log_warning "Backup failed, continuing with update..."
}

echo ""

# Pull latest changes (if in git repo)
if [ -d ".git" ]; then
    log_info "Pulling latest changes from git..."
    git pull || {
        log_error "Failed to pull latest changes"
        exit 1
    }
    log_success "Git repository updated"
    echo ""
fi

# Build new image
log_info "Building new Docker image..."
docker compose -f "$SCRIPT_DIR/docker-compose.yml" build --pull || {
    log_error "Failed to build new image"
    exit 1
}
log_success "Docker image built"
echo ""

# Restart containers with new image
log_info "Restarting containers with new image..."
docker compose -f "$SCRIPT_DIR/docker-compose.yml" up -d --force-recreate || {
    log_error "Failed to restart containers"
    exit 1
}
log_success "Containers restarted"
echo ""

# Cleanup old images
log_info "Cleaning up old images..."
docker image prune -f
log_success "Cleanup completed"
echo ""

# Health check
log_info "Running health check..."
sleep 5
"$SCRIPT_DIR/healthcheck.sh" || {
    log_warning "Health check reported issues"
}

echo ""
echo "====================================="
echo "Update completed!"
echo "====================================="
echo ""
