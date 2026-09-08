#!/usr/bin/env bash
# ==============================================================================
# WAHA Suite - Complete Backup Script
# Creates a timestamped archive containing:
#   1. WhatsApp auth sessions (sessions/)
#   2. Bot Builder database & flows (bot-builder/data/bot.db)
#   3. Keyword rules (bot/rules.json)
#   4. Environment configurations (.env)
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

TIMESTAMP="$(date +'%Y-%m-%d_%H%M%S')"
BACKUP_DIR="${SCRIPT_DIR}/backups"
ARCHIVE_NAME="waha-backup-${TIMESTAMP}.tar.gz"
TEMP_DIR="$(mktemp -d -t waha-backup-XXXXXX)"

mkdir -p "$BACKUP_DIR"

echo "=================================================="
echo " Starting WAHA Suite Backup ($TIMESTAMP)"
echo "=================================================="

cleanup() {
    rm -rf "$TEMP_DIR"
}
trap cleanup EXIT

# 1. Copy .env
if [ -f .env ]; then
    echo "[+] Backing up .env configuration..."
    cp .env "$TEMP_DIR/.env"
else
    echo "[!] Warning: .env not found in $SCRIPT_DIR"
fi

# 2. Backup Bot Builder SQLite Database safely
if [ -f "bot-builder/data/bot.db" ]; then
    echo "[+] Backing up Bot Builder database (bot.db)..."
    mkdir -p "$TEMP_DIR/bot-builder/data"
    if command -v sqlite3 >/dev/null 2>&1; then
        sqlite3 "bot-builder/data/bot.db" ".backup '$TEMP_DIR/bot-builder/data/bot.db'"
    else
        cp "bot-builder/data/bot.db" "$TEMP_DIR/bot-builder/data/bot.db"
    fi
fi

# 3. Backup Rules
if [ -f "bot/rules.json" ]; then
    echo "[+] Backing up keyword rules (bot/rules.json)..."
    mkdir -p "$TEMP_DIR/bot"
    cp "bot/rules.json" "$TEMP_DIR/bot/rules.json"
fi

# 4. Backup WhatsApp Session data (tokens, keys, sqlite)
if [ -d "sessions" ]; then
    echo "[+] Backing up WhatsApp sessions directory..."
    mkdir -p "$TEMP_DIR/sessions"
    cp -r sessions/* "$TEMP_DIR/sessions/" 2>/dev/null || true
fi

# 5. Create compressed archive
DEST_ARCHIVE="${BACKUP_DIR}/${ARCHIVE_NAME}"
echo "[+] Compressing backup archive..."
tar -czf "$DEST_ARCHIVE" -C "$TEMP_DIR" .

ARCHIVE_SIZE="$(du -h "$DEST_ARCHIVE" | cut -f1)"
ARCHIVE_SHA="$(sha256sum "$DEST_ARCHIVE" | awk '{print $1}')"

echo ""
echo "=================================================="
echo " Backup Completed Successfully!"
echo "=================================================="
echo " Archive:  $DEST_ARCHIVE"
echo " Size:     $ARCHIVE_SIZE"
echo " SHA256:   $ARCHIVE_SHA"
echo ""
echo "To copy this backup to another server:"
echo "  scp $DEST_ARCHIVE user@new-server-ip:/opt/waha/"
echo "Then on the new server, restore with:"
echo "  cd /opt/waha && ./restore.sh $ARCHIVE_NAME"
echo "=================================================="
