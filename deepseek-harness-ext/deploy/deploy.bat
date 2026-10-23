@echo off
REM =============================================================================
REM DeepSeek Harness - Docker Deployment Script for Windows
REM =============================================================================
REM This script provides commands for building, running, and managing
REM DeepSeek Harness Docker containers on Windows.
REM
REM Usage:
REM   deploy.bat [command] [options]
REM =============================================================================

setlocal enabledelayedexpansion

REM Configuration
set SCRIPT_DIR=%~dp0
set PROJECT_DIR=%SCRIPT_DIR%..\..\deepseek-harness
set COMPOSE_FILE=%SCRIPT_DIR%docker-compose.yml
set COMPOSE_DEV_FILE=%SCRIPT_DIR%docker-compose.dev.yml
set IMAGE_NAME=deepseek-harness
set CONTAINER_NAME=deepseek-harness

REM Check if Docker is running
docker info >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker is not running. Please start Docker and try again.
    exit /b 1
)

REM Commands
if "%1"=="build" goto :build
if "%1"=="up" goto :up
if "%1"=="start" goto :up
if "%1"=="down" goto :down
if "%1"=="stop" goto :down
if "%1"=="restart" goto :restart
if "%1"=="logs" goto :logs
if "%1"=="shell" goto :shell
if "%1"=="status" goto :status
if "%1"=="run" goto :run
if "%1"=="clean" goto :clean
if "%1"=="help" goto :help
if "%1"=="--help" goto :help
if "%1"=="-h" goto :help
if "%1"=="" goto :help

echo [ERROR] Unknown command: %1
echo.
goto :help

:build
echo [INFO] Building Docker image...
cd /d "%PROJECT_DIR%"
if "%2"=="--dev" (
    echo [INFO] Building development image...
    docker compose -f "%COMPOSE_FILE%" -f "%COMPOSE_DEV_FILE%" build
) else (
    docker compose -f "%COMPOSE_FILE%" build
)
echo [SUCCESS] Docker image built successfully!
goto :eof

:up
echo [INFO] Starting containers...
cd /d "%PROJECT_DIR%"
if "%2"=="--dev" (
    echo [INFO] Starting in development mode...
    docker compose -f "%COMPOSE_FILE%" -f "%COMPOSE_DEV_FILE%" up -d
) else (
    docker compose -f "%COMPOSE_FILE%" up -d
)
echo [SUCCESS] Containers started successfully!
goto :status

:down
echo [INFO] Stopping containers...
cd /d "%PROJECT_DIR%"
docker compose -f "%COMPOSE_FILE%" down
echo [SUCCESS] Containers stopped successfully!
goto :eof

:restart
call :down
call :up %2
goto :eof

:logs
cd /d "%PROJECT_DIR%"
set SERVICE=%2
if "%SERVICE%"=="" set SERVICE=dsh
if "%3"=="-f" (
    docker compose -f "%COMPOSE_FILE%" logs -f %SERVICE%
) else (
    docker compose -f "%COMPOSE_FILE%" logs --tail=100 %SERVICE%
)
goto :eof

:shell
cd /d "%PROJECT_DIR%"
set SERVICE=%2
if "%SERVICE%"=="" set SERVICE=dsh
echo [INFO] Opening shell in %SERVICE% container...
docker compose -f "%COMPOSE_FILE%" exec %SERVICE% /bin/sh
goto :eof

:status
echo.
echo [INFO] Container Status:
echo ===================
cd /d "%PROJECT_DIR%"
docker compose -f "%COMPOSE_FILE%" ps
echo.
goto :eof

:run
if "%2"=="" (
    echo [ERROR] Please specify a task to run
    echo Usage: deploy.bat run "task description"
    exit /b 1
)
echo [INFO] Running task: %2
cd /d "%PROJECT_DIR%"
docker compose -f "%COMPOSE_FILE%" run --rm dsh node --import tsx/esm apps/cli/src/bin.ts %2
goto :eof

:clean
echo [WARNING] This will remove all containers, images, and volumes!
set /p CONFIRM="Are you sure? (y/N) "
if /i "%CONFIRM%"=="y" (
    echo [INFO] Cleaning up...
    cd /d "%PROJECT_DIR%"
    docker compose -f "%COMPOSE_FILE%" down -v --rmi local
    docker image prune -f
    echo [SUCCESS] Cleanup completed!
) else (
    echo [INFO] Cleanup cancelled.
)
goto :eof

:help
echo DeepSeek Harness Docker Deployment Script for Windows
echo.
echo Usage: deploy.bat [command] [options]
echo.
echo Commands:
echo   build [--dev]     Build the Docker image (use --dev for development)
echo   up [--dev]        Start the containers (use --dev for development mode)
echo   down              Stop and remove containers
echo   restart [--dev]   Restart the containers
echo   logs [service]    View container logs (default service: dsh)
echo   logs [service] -f Follow log output
echo   shell [service]   Open a shell in the running container
echo   status            Show container status
echo   run "task"        Run a task in a new container
echo   clean             Remove all containers, images, and volumes
echo   help              Show this help message
echo.
echo Examples:
echo   deploy.bat build                  REM Build production image
echo   deploy.bat up                     REM Start in production mode
echo   deploy.bat up --dev               REM Start in development mode
echo   deploy.bat logs dsh -f            REM Follow logs
echo   deploy.bat shell                  REM Open shell in container
echo   deploy.bat run "analyze code"     REM Run a task
echo.
echo Environment Variables:
echo   DEEPSEEK_API_KEY    Your DeepSeek API key
echo   DEEPSEEK_BASE_URL   Custom API base URL (optional)
echo   DSH_WEB_PORT        Web UI port (default: 3000)
echo.
goto :eof
