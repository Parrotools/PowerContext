#!/usr/bin/env bash
# 知序 (ZhiXu) Learning Assistant — One-click startup
# Requires: Docker, Docker Compose

set -e

echo "========================================="
echo "  知序 — 智能学习助手"
echo "  ZhiXu Learning Assistant"
echo "========================================="
echo ""

cd "$(dirname "$0")"

# Check Docker
if ! command -v docker &> /dev/null; then
    echo "[ERROR] Docker not found. Please install Docker first."
    echo "  https://docs.docker.com/get-docker/"
    exit 1
fi

if ! docker compose version &> /dev/null && ! docker-compose version &> /dev/null; then
    echo "[ERROR] Docker Compose not found."
    exit 1
fi

# Use docker compose (v2) or docker-compose (v1)
COMPOSE="docker compose"
if ! docker compose version &> /dev/null; then
    COMPOSE="docker-compose"
fi

echo "[1/3] Building and starting services..."
$COMPOSE up -d --build

echo ""
echo "[2/3] Waiting for services to be ready..."
for i in $(seq 1 30); do
    if curl -sf http://localhost:8000/api/health > /dev/null 2>&1; then
        break
    fi
    sleep 2
done

echo ""
echo "[3/3] Checking service status..."
echo ""

# Health check
HEALTH=$(curl -sf http://localhost:8000/api/health 2>/dev/null || echo '{"error":"timeout"}')
echo "  Backend:     http://localhost:8000"
echo "  Health:      $HEALTH"
echo ""
echo "  PowerContext: http://localhost:8010"
echo ""

# Check if sample data exists
DOC_COUNT=$(curl -sf http://localhost:8000/api/knowledge/documents 2>/dev/null | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
echo "  Knowledge base: $DOC_COUNT documents loaded"
echo ""

echo "========================================="
echo "  Services are running!"
echo ""
echo "  API docs:    http://localhost:8000/docs"
echo "  Frontend:    cd frontend && npm run dev"
echo ""
echo "  Quick test:"
echo "    curl http://localhost:8000/api/health"
echo "    curl 'http://localhost:8000/api/knowledge/search?q=tree'"
echo "========================================="
