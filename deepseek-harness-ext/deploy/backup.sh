#!/bin/bash
# =============================================================================
# DeepSeek Harness - Docker Backup Script
# =============================================================================
# This script backs up DeepSeek Harness data (config, sessions, logs)
# =============================================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")/deepseek-harness"

# Configuration
BACKUP_DIR="${1:-./backups}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_NAME="dsh_backup_${TIMESTAMP}"

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

echo ""
echo "====================================="
echo "DeepSeek Harness Backup"
echo "====================================="
echo ""

# Create backup directory
mkdir -p "$BACKUP_DIR"

log_info "Creating backup: $BACKUP_NAME"
log_info "Backup directory: $BACKUP_DIR"
echo ""

# Backup volumes
log_info "Backing up Docker volumes..."

cd "$PROJECT_DIR"

# Get volume names
CONFIG_VOLUME="deepseek-harness-config"
SESSIONS_VOLUME="deepseek-harness-sessions"
LOGS_VOLUME="deepseek-harness-logs"

# Backup config volume
if docker volume inspect "$CONFIG_VOLUME" > /dev/null 2>&1; then
    log_info "Backing up config volume..."
    docker run --rm \
        -v "$CONFIG_VOLUME":/volume:ro \
        -v "$BACKUP_DIR":/backup \
        alpine tar czf "/backup/${BACKUP_NAME}_config.tar.gz" -C /volume .
    log_success "Config volume backed up"
else
    log_info "Config volume not found (skipping)"
fi

# Backup sessions volume
if docker volume inspect "$SESSIONS_VOLUME" > /dev/null 2>&1; then
    log_info "Backing up sessions volume..."
    docker run --rm \
        -v "$SESSIONS_VOLUME":/volume:ro \
        -v "$BACKUP_DIR":/backup \
        alpine tar czf "/backup/${BACKUP_NAME}_sessions.tar.gz" -C /volume .
    log_success "Sessions volume backed up"
else
    log_info "Sessions volume not found (skipping)"
fi

# Backup logs volume
if docker volume inspect "$LOGS_VOLUME" > /dev/null 2>&1; then
    log_info "Backing up logs volume..."
    docker run --rm \
        -v "$LOGS_VOLUME":/volume:ro \
        -v "$BACKUP_DIR":/backup \
        alpine tar czf "/backup/${BACKUP_NAME}_logs.tar.gz" -C /volume .
    log_success "Logs volume backed up"
else
    log_info "Logs volume not found (skipping)"
fi

# Create manifest
cat > "$BACKUP_DIR/${BACKUP_NAME}_manifest.json" << EOF
{
  "backup_name": "$BACKUP_NAME",
  "timestamp": "$TIMESTAMP",
  "date": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "volumes": {
    "config": "$CONFIG_VOLUME",
    "sessions": "$SESSIONS_VOLUME",
    "logs": "$LOGS_VOLUME"
  }
}
EOF

echo ""
log_success "Backup completed!"
echo ""
echo "Backup files:"
ls -lh "$BACKUP_DIR"/${BACKUP_NAME}* | sed 's/^/  /'
echo ""
