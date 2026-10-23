#!/bin/bash
# =============================================================================
# DeepSeek Harness - Docker Restore Script
# =============================================================================
# This script restores DeepSeek Harness data from a backup
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

usage() {
    echo "Usage: $0 <backup-name>"
    echo ""
    echo "Example:"
    echo "  $0 dsh_backup_20260916_120000"
    echo ""
    echo "Available backups:"
    ls -1 ./backups/ 2>/dev/null | grep "_manifest.json" | sed 's/_manifest.json//' | sed 's/^/  /' || echo "  No backups found"
    exit 1
}

if [ -z "$1" ]; then
    usage
fi

BACKUP_NAME="$1"
BACKUP_DIR="./backups"

echo ""
echo "====================================="
echo "DeepSeek Harness Restore"
echo "====================================="
echo ""

# Check if backup exists
if [ ! -f "$BACKUP_DIR/${BACKUP_NAME}_manifest.json" ]; then
    log_error "Backup not found: $BACKUP_NAME"
    echo ""
    echo "Available backups:"
    ls -1 "$BACKUP_DIR" 2>/dev/null | grep "_manifest.json" | sed 's/_manifest.json//' | sed 's/^/  /' || echo "  No backups found"
    exit 1
fi

log_info "Restoring from backup: $BACKUP_NAME"
log_warning "This will overwrite existing data!"
echo ""
read -p "Are you sure? (y/N) " -n 1 -r
echo

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    log_info "Restore cancelled."
    exit 0
fi

# Stop containers
log_info "Stopping containers..."
cd "$PROJECT_DIR"
docker compose -f "$SCRIPT_DIR/docker-compose.yml" down || true

# Restore config volume
if [ -f "$BACKUP_DIR/${BACKUP_NAME}_config.tar.gz" ]; then
    log_info "Restoring config volume..."
    docker volume create deepseek-harness-config 2>/dev/null || true
    docker run --rm \
        -v deepseek-harness-config:/volume \
        -v "$BACKUP_DIR":/backup:ro \
        alpine sh -c "cd /volume && tar xzf /backup/${BACKUP_NAME}_config.tar.gz"
    log_success "Config volume restored"
fi

# Restore sessions volume
if [ -f "$BACKUP_DIR/${BACKUP_NAME}_sessions.tar.gz" ]; then
    log_info "Restoring sessions volume..."
    docker volume create deepseek-harness-sessions 2>/dev/null || true
    docker run --rm \
        -v deepseek-harness-sessions:/volume \
        -v "$BACKUP_DIR":/backup:ro \
        alpine sh -c "cd /volume && tar xzf /backup/${BACKUP_NAME}_sessions.tar.gz"
    log_success "Sessions volume restored"
fi

# Restore logs volume
if [ -f "$BACKUP_DIR/${BACKUP_NAME}_logs.tar.gz" ]; then
    log_info "Restoring logs volume..."
    docker volume create deepseek-harness-logs 2>/dev/null || true
    docker run --rm \
        -v deepseek-harness-logs:/volume \
        -v "$BACKUP_DIR":/backup:ro \
        alpine sh -c "cd /volume && tar xzf /backup/${BACKUP_NAME}_logs.tar.gz"
    log_success "Logs volume restored"
fi

echo ""
log_success "Restore completed!"
echo ""
log_info "You can now start the containers:"
echo "  ./deploy.sh up"
echo ""
