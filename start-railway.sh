#!/bin/bash

# Script de démarrage pour Railway
# Lance à la fois le backend Python et le watcher Telegram

set -e

echo "=========================================="
echo "Starting Alyn on Railway"
echo "=========================================="

# Vérifier les variables d'environnement critiques
if [ -z "$TELEGRAM_BOT_TOKEN" ]; then
    echo "⚠️  WARNING: TELEGRAM_BOT_TOKEN not set. Telegram watcher will not start."
    TELEGRAM_ENABLED=false
else
    echo "✅ TELEGRAM_BOT_TOKEN found"
    TELEGRAM_ENABLED=true
fi

if [ -z "$OPENROUTER_API_KEY" ]; then
    echo "❌ ERROR: OPENROUTER_API_KEY not set!"
    exit 1
fi

echo "✅ OPENROUTER_API_KEY found"

# Lancer le backend FastAPI en arrière-plan
echo ""
echo "Starting FastAPI backend..."
python -m server.server &
BACKEND_PID=$!
echo "✅ Backend started (PID: $BACKEND_PID)"

# Attendre que le backend soit prêt
echo "Waiting for backend to be ready..."
for i in {1..30}; do
    if curl -s http://localhost:8001/health > /dev/null 2>&1; then
        echo "✅ Backend is ready!"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "❌ Backend failed to start within 30 seconds"
        exit 1
    fi
    sleep 1
done

# Lancer le watcher Telegram si configuré
if [ "$TELEGRAM_ENABLED" = true ]; then
    echo ""
    echo "Starting Telegram watcher..."

    # Configurer pour utiliser le backend local
    export BACKEND_MODE=LOCAL

    cd /app
    node server/services/telegram/telegram_watcher.js &
    WATCHER_PID=$!
    echo "✅ Telegram watcher started (PID: $WATCHER_PID)"
else
    echo ""
    echo "⚠️  Telegram watcher not started (TELEGRAM_BOT_TOKEN not set)"
fi

echo ""
echo "=========================================="
echo "Alyn is running on Railway"
echo "Backend PID: $BACKEND_PID"
if [ "$TELEGRAM_ENABLED" = true ]; then
    echo "Watcher PID: $WATCHER_PID"
fi
echo "=========================================="

# Attendre que les processus se terminent (ne devrait jamais arriver)
wait $BACKEND_PID
