#!/bin/bash
# =============================================================================
# DeepSeek Harness - Docker Deployment Script
# =============================================================================
# This script provides commands for building, running, and managing
# DeepSeek Harness Docker containers.
#
# Usage:
#   ./deploy.sh [command] [options]
#
# Commands:
#   build       - Build the Docker image
#   up          - Start the containers
#   down        - Stop and remove containers
#   restart     - Restart the containers
#   logs        - View container logs
#   shell       - Open a shell in the running container
#   status      - Show container status
#   clean       - Remove all containers, images, and volumes
#   help        - Show this help message
# =============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")/deepseek-harness"
COMPOSE_FILE="$SCRIPT_DIR/docker-compose.yml"
COMPOSE_DEV_FILE="$SCRIPT_DIR/docker-compose.dev.yml"
IMAGE_NAME="deepseek-harness"
CONTAINER_NAME="deepseek-harness"

# Functions
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

# Check if Docker is running
check_docker() {
    if ! docker info > /dev/null 2>&1; then
        log_error "Docker is not running. Please start Docker and try again."
        exit 1
    fi
}

# Check if docker compose is available
check_compose() {
    if ! docker compose version &> /dev/null; then
        log_error "docker compose is not installed. Please install it and try again."
        exit 1
    fi
}

# Build Docker image
cmd_build() {
    check_docker
    log_info "Building Docker image..."

    cd "$PROJECT_DIR"

    if [ "$1" == "--dev" ]; then
        log_info "Building development image..."
        docker compose -f "$COMPOSE_FILE" -f "$COMPOSE_DEV_FILE" build
    else
        docker compose -f "$COMPOSE_FILE" build
    fi

    log_success "Docker image built successfully!"
}

# Start containers
cmd_up() {
    check_docker
    check_compose
    log_info "Starting containers..."

    cd "$PROJECT_DIR"

    if [ "$1" == "--dev" ]; then
        log_info "Starting in development mode..."
        docker compose -f "$COMPOSE_FILE" -f "$COMPOSE_DEV_FILE" up -d
    else
        docker compose -f "$COMPOSE_FILE" up -d
    fi

    log_success "Containers started successfully!"
    cmd_status
}

# Stop containers
cmd_down() {
    check_docker
    check_compose
    log_info "Stopping containers..."

    cd "$PROJECT_DIR"
    docker compose -f "$COMPOSE_FILE" down

    log_success "Containers stopped successfully!"
}

# Restart containers
cmd_restart() {
    log_info "Restarting containers..."
    cmd_down
    cmd_up "$@"
}

# View logs
cmd_logs() {
    check_docker
    check_compose

    local service="${1:-dsh}"
    local follow="${2:-}"

    cd "$PROJECT_DIR"

    if [ "$follow" == "-f" ] || [ "$follow" == "--follow" ]; then
        docker compose -f "$COMPOSE_FILE" logs -f "$service"
    else
        docker compose -f "$COMPOSE_FILE" logs --tail=100 "$service"
    fi
}

# Open shell in container
cmd_shell() {
    check_docker

    local service="${1:-dsh}"

    log_info "Opening shell in $service container..."
    docker compose -f "$COMPOSE_FILE" exec "$service" /bin/sh
}

# Show status
cmd_status() {
    check_docker
    check_compose

    echo ""
    log_info "Container Status:"
    echo "==================="
    docker compose -f "$COMPOSE_FILE" ps
    echo ""
}

# Clean up everything
cmd_clean() {
    check_docker
    check_compose

    log_warning "This will remove all containers, images, and volumes!"
    read -p "Are you sure? (y/N) " -n 1 -r
    echo

    if [[ $REPLY =~ ^[Yy]$ ]]; then
        log_info "Cleaning up..."

        cd "$PROJECT_DIR"

        # Stop and remove containers
        docker compose -f "$COMPOSE_FILE" down -v --rmi local

        # Remove dangling images
        docker image prune -f

        log_success "Cleanup completed!"
    else
        log_info "Cleanup cancelled."
    fi
}

# Run a task
cmd_run() {
    check_docker
    check_compose

    if [ -z "$1" ]; then
        log_error "Please specify a task to run"
        echo "Usage: $0 run <task>"
        echo "Example: $0 run \"summarize this codebase\""
        exit 1
    fi

    local task="$@"
    log_info "Running task: $task"

    cd "$PROJECT_DIR"
    docker compose -f "$COMPOSE_FILE" run --rm dsh node --import tsx/esm apps/cli/src/bin.ts "$task"
}

# Show help
cmd_help() {
    echo "DeepSeek Harness Docker Deployment Script"
    echo ""
    echo "Usage: $0 [command] [options]"
    echo ""
    echo "Commands:"
    echo "  build [--dev]     Build the Docker image (use --dev for development)"
    echo "  up [--dev]        Start the containers (use --dev for development mode)"
    echo "  down              Stop and remove containers"
    echo "  restart [--dev]   Restart the containers"
    echo "  logs [service]    View container logs (default service: dsh)"
    echo "  logs [service] -f Follow log output"
    echo "  shell [service]   Open a shell in the running container"
    echo "  status            Show container status"
    echo "  run <task>        Run a task in a new container"
    echo "  clean             Remove all containers, images, and volumes"
    echo "  help              Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 build                  # Build production image"
    echo "  $0 up                     # Start in production mode"
    echo "  $0 up --dev               # Start in development mode"
    echo "  $0 logs dsh -f            # Follow logs"
    echo "  $0 shell                  # Open shell in container"
    echo "  $0 run 'analyze code'     # Run a task"
    echo ""
    echo "Environment Variables:"
    echo "  DEEPSEEK_API_KEY    Your DeepSeek API key"
    echo "  DEEPSEEK_BASE_URL   Custom API base URL (optional)"
    echo "  DSH_WEB_PORT        Web UI port (default: 3000)"
    echo "  TZ                  Timezone (default: UTC)"
    echo ""
}

# Main command router
main() {
    local command="${1:-help}"
    shift || true

    case "$command" in
        build)
            cmd_build "$@"
            ;;
        up|start)
            cmd_up "$@"
            ;;
        down|stop)
            cmd_down
            ;;
        restart)
            cmd_restart "$@"
            ;;
        logs)
            cmd_logs "$@"
            ;;
        shell|bash|sh)
            cmd_shell "$@"
            ;;
        status|ps)
            cmd_status
            ;;
        run|exec)
            cmd_run "$@"
            ;;
        clean|cleanup)
            cmd_clean
            ;;
        help|--help|-h)
            cmd_help
            ;;
        *)
            log_error "Unknown command: $command"
            echo ""
            cmd_help
            exit 1
            ;;
    esac
}

# Run main function
main "$@"
