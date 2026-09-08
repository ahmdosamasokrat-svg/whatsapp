#!/usr/bin/env bash
# ==============================================================================
# WAHA Suite - Restore Script
# Restores .env, sessions, bot.db, and rules from a backup archive.
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ $# -lt 1 ]; then
    echo "Usage: $0 <path-to-waha-backup.tar.gz>"
    echo ""
    echo "Available backups in ./backups:"
    ls -lh backups/*.tar.gz 2>/dev/null || echo "  (no backups found in ./backups/)"
    exit 1
fi

ARCHIVE_PATH="$1"

if [ ! -f "$ARCHIVE_PATH" ] && [ -f "backups/$ARCHIVE_PATH" ]; then
    ARCHIVE_PATH="backups/$ARCHIVE_PATH"
fi

if [ ! -f "$ARCHIVE_PATH" ]; then
    echo "[-] Error: Archive not found: $ARCHIVE_PATH"
    exit 1
fi

echo "=================================================="
echo " Restoring WAHA Suite from: $ARCHIVE_PATH"
echo "=================================================="

# Prompt confirmation
if [ -t 0 ]; then
    read -r -p "This will overwrite existing session data and database. Continue? [y/N] " CONFIRM
    if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
        echo "Aborted."
        exit 0
    fi
fi

# Stop containers if running
if command -v docker >/dev/null 2>&1; then
    echo "[+] Stopping running containers..."
    docker compose down 2>/dev/null || true
fi

TEMP_EXTRACT="$(mktemp -d -t waha-restore-XXXXXX)"
cleanup() {
    rm -rf "$TEMP_EXTRACT"
}
trap cleanup EXIT

echo "[+] Extracting archive..."
tar -xzf "$ARCHIVE_PATH" -C "$TEMP_EXTRACT"

# 1. Restore .env
if [ -f "$TEMP_EXTRACT/.env" ]; then
    echo "[+] Restoring .env..."
    cp "$TEMP_EXTRACT/.env" .env
fi

# 2. Restore sessions
if [ -d "$TEMP_EXTRACT/sessions" ]; then
    echo "[+] Restoring WhatsApp sessions..."
    mkdir -p sessions
    cp -r "$TEMP_EXTRACT/sessions/"* sessions/ 2>/dev/null || true
fi

# 3. Restore bot.db
if [ -f "$TEMP_EXTRACT/bot-builder/data/bot.db" ]; then
    echo "[+] Restoring Bot Builder database..."
    mkdir -p bot-builder/data
    cp "$TEMP_EXTRACT/bot-builder/data/bot.db" bot-builder/data/bot.db
fi

# 4. Restore rules.json
if [ -f "$TEMP_EXTRACT/bot/rules.json" ]; then
    echo "[+] Restoring rules.json..."
    mkdir -p bot
    cp "$TEMP_EXTRACT/bot/rules.json" bot/rules.json
fi

echo "=================================================="
echo " Restore complete! Starting containers..."
echo "=================================================="
if command -v docker >/dev/null 2>&1; then
    docker compose up -d
    echo "[+] Containers started successfully!"
fi
echo "=================================================="
