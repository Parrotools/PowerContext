@echo off
REM 知序 (ZhiXu) Learning Assistant — One-click startup (Windows)
REM Requires: Docker Desktop

echo =========================================
echo   知序 — 智能学习助手
echo   ZhiXu Learning Assistant
echo =========================================
echo.

cd /d "%~dp0"

REM Check Docker
docker version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker not found. Please install Docker Desktop first.
    echo   https://docs.docker.com/desktop/install/windows-install/
    pause
    exit /b 1
)

echo [1/3] Building and starting services...
docker compose up -d --build
if errorlevel 1 (
    echo [ERROR] docker compose failed, trying docker-compose...
    docker-compose up -d --build
)

echo.
echo [2/3] Waiting for services to be ready...
timeout /t 10 /nobreak >nul

echo.
echo [3/3] Checking service status...
echo.

curl -sf http://localhost:8000/api/health >nul 2>&1
if errorlevel 1 (
    echo   [WARN] Backend not ready yet, waiting 10 more seconds...
    timeout /t 10 /nobreak >nul
)

echo   Backend:      http://localhost:8000
echo   API docs:     http://localhost:8000/docs
echo   PowerContext: http://localhost:8010
echo.

echo   Quick test:
echo     curl http://localhost:8000/api/health
echo     curl "http://localhost:8000/api/knowledge/search?q=binary+tree"
echo.
echo =========================================
echo   Services are running!
echo   Frontend: cd frontend ^&^& npm run dev
echo =========================================
pause
