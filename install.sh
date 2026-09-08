#!/usr/bin/env bash
# ==============================================================================
# WAHA Suite - Automated Installer & Deployer
# WhatsApp HTTP API + Visual Flow Builder + Contacts Manager + Admin Rules
#
# Supported OS:
#   - Rocky Linux / AlmaLinux / CentOS / RHEL (8, 9)
#   - Ubuntu (20.04, 22.04, 24.04)
#   - Debian (11, 12)
#   - Fedora
# ==============================================================================
set -euo pipefail

# Text formatting
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

INSTALL_DIR="/opt/waha"
DEFAULT_REPO_URL="https://github.com/ahmdosamasokrat-svg/whatsapp.git"

echo -e "${CYAN}${BOLD}"
cat << "EOF"
 __          __     _    _          _____       _ _       
 \ \        / /\   | |  | |   /\   / ____|     (_) |      
  \ \  /\  / /  \  | |__| |  /  \ | (___  _   _ _| |_ ___ 
   \ \/  \/ / /\ \ |  __  | / /\ \ \___ \| | | | | __/ _ \
    \  /\  / ____ \| |  | |/ ____ \____) | |_| | | ||  __/
     \/  \/_/    \_\_|  |_/_/    \_\_____/ \__,_|_|\__\___|
       WhatsApp API + Visual Flow Builder + Contacts Suite
EOF
echo -e "${NC}"
echo -e "${BLUE}==============================================================${NC}"
echo -e "${BOLD} Starting WAHA Suite Installation${NC}"
echo -e "${BLUE}==============================================================${NC}"
get_env_val() {
    local key="$1"
    local default_val="${2:-}"
    local val
    val=$(grep "^${key}=" .env 2>/dev/null | cut -d= -f2- | tr -d '\r' | tr -d "'" | tr -d '"' || true)
    if [ -n "$val" ]; then
        echo "$val"
    else
        echo "$default_val"
    fi
}


# 1. Root check
if [ "$(id -u)" -ne 0 ]; then
    echo -e "${RED}[-] This script must be run as root (or via sudo).${NC}"
    exit 1
fi

# 2. Check if running from within cloned repo or from curl/pipe
RUNNING_INSIDE_REPO=false
if [ -f "./docker-compose.yml" ] && [ -d "./bot-builder" ] && [ -d "./contacts-ui" ]; then
    RUNNING_INSIDE_REPO=true
    INSTALL_DIR="$(pwd)"
elif [ -f "$INSTALL_DIR/docker-compose.yml" ] && [ -d "$INSTALL_DIR/bot-builder" ]; then
    RUNNING_INSIDE_REPO=true
fi

# 3. Detect Package Manager and OS
echo -e "${BLUE}[1/8] Detecting Operating System...${NC}"
PKG_MANAGER=""
if command -v dnf >/dev/null 2>&1; then
    PKG_MANAGER="dnf"
elif command -v yum >/dev/null 2>&1; then
    PKG_MANAGER="yum"
elif command -v apt-get >/dev/null 2>&1; then
    PKG_MANAGER="apt-get"
else
    echo -e "${RED}[-] Unsupported package manager. Please install dependencies manually.${NC}"
    exit 1
fi
echo -e "${GREEN}[+] Detected package manager: ${PKG_MANAGER}${NC}"

# 4. Install prerequisites
echo -e "${BLUE}[2/8] Installing core system packages (curl, git, jq, openssl, tar)...${NC}"
if [ "$PKG_MANAGER" = "apt-get" ]; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -y
    apt-get install -y curl git jq openssl tar ca-certificates gnupg
elif [ "$PKG_MANAGER" = "dnf" ] || [ "$PKG_MANAGER" = "yum" ]; then
    $PKG_MANAGER install -y curl git jq openssl tar
fi
echo -e "${GREEN}[+] System packages installed successfully.${NC}"

# 5. Install Docker & Docker Compose if missing
echo -e "${BLUE}[3/8] Checking Docker & Docker Compose...${NC}"
if ! command -v docker >/dev/null 2>&1; then
    echo -e "${YELLOW}[!] Docker not found. Installing official Docker...${NC}"
    curl -fsSL https://get.docker.com | sh
    systemctl daemon-reload || true
fi

systemctl enable --now docker || systemctl start docker || true

# Verify docker compose plugin
if ! docker compose version >/dev/null 2>&1; then
    echo -e "${YELLOW}[!] Docker Compose plugin missing. Installing docker-compose-plugin...${NC}"
    if [ "$PKG_MANAGER" = "apt-get" ]; then
        apt-get install -y docker-compose-plugin || true
    elif [ "$PKG_MANAGER" = "dnf" ] || [ "$PKG_MANAGER" = "yum" ]; then
        $PKG_MANAGER install -y docker-compose-plugin || true
    fi
fi

if ! docker compose version >/dev/null 2>&1; then
    echo -e "${RED}[-] Docker Compose plugin could not be verified. Please ensure Docker Compose V2 is installed.${NC}"
    exit 1
fi
echo -e "${GREEN}[+] Docker version: $(docker --version)${NC}"
echo -e "${GREEN}[+] Docker Compose: $(docker compose version)${NC}"

# 6. Setup Directory and Clone if needed
echo -e "${BLUE}[4/8] Setting up installation directory at ${INSTALL_DIR}...${NC}"
if [ "$RUNNING_INSIDE_REPO" = false ]; then
    mkdir -p "$INSTALL_DIR"
    if [ -d "$INSTALL_DIR/.git" ]; then
        echo -e "${CYAN}[+] Existing git repository found in ${INSTALL_DIR}. Pulling latest changes...${NC}"
        cd "$INSTALL_DIR"
        git pull || true
    else
        REPO_INPUT=""
        if [ -t 0 ]; then
            read -r -p "Enter your GitHub repository URL (press Enter for current folder): " REPO_INPUT
        fi
        if [ -n "$REPO_INPUT" ]; then
            echo -e "${CYAN}[+] Cloning ${REPO_INPUT} into ${INSTALL_DIR}...${NC}"
            git clone "$REPO_INPUT" "$INSTALL_DIR"
            cd "$INSTALL_DIR"
        else
            echo -e "${CYAN}[+] Copying files to ${INSTALL_DIR}...${NC}"
            cp -r ./* "$INSTALL_DIR/" 2>/dev/null || true
            cd "$INSTALL_DIR"
        fi
    fi
else
    cd "$INSTALL_DIR"
fi

# Ensure subdirectories exist
mkdir -p sessions media bot-builder/data bot backups

# 7. Configure Environment (.env)
echo -e "${BLUE}[5/8] Configuring environment variables (.env)...${NC}"
if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        cp .env.example .env
    else
        touch .env
    fi

    echo -e "${CYAN}[+] Generating secure random secrets...${NC}"
    RANDOM_API_KEY="$(openssl rand -hex 24)"
    RANDOM_DASH_PASS="$(openssl rand -base64 12 | tr -dc 'a-zA-Z0-9' | head -c 16)"
    RANDOM_SWAG_PASS="$(openssl rand -base64 12 | tr -dc 'a-zA-Z0-9' | head -c 16)"
    RANDOM_BOT_ADMIN_PASS="Admin@$(openssl rand -hex 4)"
    RANDOM_ADMIN_SECRET="$(openssl rand -hex 32)"

    # Set values in .env
    sed -i "s|^WAHA_API_KEY=.*|WAHA_API_KEY=${RANDOM_API_KEY}|" .env || echo "WAHA_API_KEY=${RANDOM_API_KEY}" >> .env
    sed -i "s|^WAHA_DASHBOARD_PASSWORD=.*|WAHA_DASHBOARD_PASSWORD=${RANDOM_DASH_PASS}|" .env || echo "WAHA_DASHBOARD_PASSWORD=${RANDOM_DASH_PASS}" >> .env
    sed -i "s|^WHATSAPP_SWAGGER_PASSWORD=.*|WHATSAPP_SWAGGER_PASSWORD=${RANDOM_SWAG_PASS}|" .env || echo "WHATSAPP_SWAGGER_PASSWORD=${RANDOM_SWAG_PASS}" >> .env
    sed -i "s|^BOT_ADMIN_PASSWORD=.*|BOT_ADMIN_PASSWORD=${RANDOM_BOT_ADMIN_PASS}|" .env || echo "BOT_ADMIN_PASSWORD=${RANDOM_BOT_ADMIN_PASS}" >> .env
    sed -i "s|^BOT_ADMIN_SECRET=.*|BOT_ADMIN_SECRET=${RANDOM_ADMIN_SECRET}|" .env || echo "BOT_ADMIN_SECRET=${RANDOM_ADMIN_SECRET}" >> .env

    chmod 600 .env
    echo -e "${GREEN}[+] Generated fresh .env with secure random passwords.${NC}"
else
    echo -e "${GREEN}[+] Existing .env file found. Preserving current configuration.${NC}"
fi

# 8. Seed Flows & Default Rules if needed
echo -e "${BLUE}[6/8] Preparing seed data and bot flows...${NC}"
if [ -f "bot-builder/data/flows_export.json" ] && [ ! -f "bot-builder/data/bot.db" ]; then
    echo -e "${CYAN}[+] flows_export.json ready for automatic seeding on startup.${NC}"
fi

if [ ! -f "bot/rules.json" ]; then
    cat > bot/rules.json << 'EOF'
{
  "exact": {
    "hello": "Hello! How can I help you today?",
    "hi": "Hello! Welcome to our automated assistant.",
    "السلام عليكم": "وعليكم السلام ورحمة الله وبركاته، أهلاً بك!"
  },
  "contains": {
    "support": "Our support team has been notified and will assist you shortly.",
    "price": "Please specify which service or package you are inquiring about.",
    "مواعيد": "مواعيد العمل الرسمية من 9 صباحاً حتى 5 مساءً."
  }
}
EOF
    echo -e "${GREEN}[+] Default keyword rules initialized in bot/rules.json${NC}"
fi

# 9. Build and Launch Containers
echo -e "${BLUE}[7/8] Building and starting WAHA Suite containers...${NC}"
docker compose pull waha || true
docker compose build
docker compose up -d

echo -e "${BLUE}[8/8] Checking service health & registering WAHA webhook...${NC}"

# Wait for WAHA to be healthy
WAHA_READY=false
for i in $(seq 1 30); do
    if curl -sf http://127.0.0.1:2000/ping >/dev/null 2>&1; then
        WAHA_READY=true
        break
    fi
    sleep 2
done

if [ "$WAHA_READY" = true ]; then
    echo -e "${GREEN}[+] WAHA HTTP API core is UP and running on port 2000.${NC}"
    
    # Configure default session webhook
    API_KEY=$(get_env_val "WAHA_API_KEY" "")
    SESSION_NAME=$(get_env_val "WAHA_SESSION" "test")

    # Check if session exists or start it
    SESSION_STATUS=$(curl -s -H "X-Api-Key: $API_KEY" http://127.0.0.1:2000/api/sessions | jq -r ".[] | select(.name==\"$SESSION_NAME\") | .status" 2>/dev/null || echo "")
    
    if [ -z "$SESSION_STATUS" ]; then
        echo -e "${CYAN}[+] Starting initial session '$SESSION_NAME'...${NC}"
        curl -s -X POST "http://127.0.0.1:2000/api/sessions" \
            -H "X-Api-Key: $API_KEY" \
            -H "Content-Type: application/json" \
            -d "{
                \"name\": \"$SESSION_NAME\",
                \"config\": {
                    \"webhooks\": [
                        {
                            \"url\": \"http://waha-bot-builder:2004/webhook/waha\",
                            \"events\": [\"message\"]
                        }
                    ]
                }
            }" >/dev/null 2>&1 || true
    else
        echo -e "${CYAN}[+] Updating session '$SESSION_NAME' webhook to Bot Builder...${NC}"
        curl -s -X PATCH "http://127.0.0.1:2000/api/sessions/$SESSION_NAME" \
            -H "X-Api-Key: $API_KEY" \
            -H "Content-Type: application/json" \
            -d "{
                \"config\": {
                    \"webhooks\": [
                        {
                            \"url\": \"http://waha-bot-builder:2004/webhook/waha\",
                            \"events\": [\"message\"]
                        }
                    ]
                }
            }" >/dev/null 2>&1 || true
    fi
else
    echo -e "${YELLOW}[!] Note: WAHA core is still starting up in the background.${NC}"
fi

# Firewall notice
if command -v ufw >/dev/null 2>&1 && ufw status | grep -q "Status: active"; then
    echo -e "${CYAN}[+] Configuring UFW firewall rules for ports 2000-2004...${NC}"
    ufw allow 2000/tcp comment "WAHA API & Dashboard" || true
    ufw allow 2001/tcp comment "WAHA Contacts UI" || true
    ufw allow 2002/tcp comment "WAHA Bot" || true
    ufw allow 2003/tcp comment "WAHA Bot Admin" || true
    ufw allow 2004/tcp comment "WAHA Bot Builder" || true
elif command -v firewall-cmd >/dev/null 2>&1 && systemctl is-active --quiet firewalld; then
    echo -e "${CYAN}[+] Configuring firewalld rules for ports 2000-2004...${NC}"
    firewall-cmd --permanent --add-port=2000-2004/tcp || true
    firewall-cmd --reload || true
fi

# Get Server IP
SERVER_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
[ -z "$SERVER_IP" ] && SERVER_IP="127.0.0.1"

# Read passwords from .env
API_KEY=$(get_env_val "WAHA_API_KEY" "")
DASH_USER=$(get_env_val "WAHA_DASHBOARD_USERNAME" "admin")
DASH_PASS=$(get_env_val "WAHA_DASHBOARD_PASSWORD" "(configured in .env)")
BOT_ADMIN_PASS=$(get_env_val "BOT_ADMIN_PASSWORD" "Admin@123")

echo ""
echo -e "${GREEN}${BOLD}==============================================================${NC}"
echo -e "${GREEN}${BOLD}       WAHA SUITE INSTALLATION COMPLETED SUCCESSFULLY!        ${NC}"
echo -e "${GREEN}${BOLD}==============================================================${NC}"
echo ""
echo -e "${BOLD}Access Endpoints & Web Portals:${NC}"
echo -e "  ${CYAN}1. Bot Flow Builder (Drag & Drop):${NC}  ${BOLD}http://${SERVER_IP}:2004${NC}"
echo -e "  ${CYAN}2. WAHA Web Dashboard:${NC}              ${BOLD}http://${SERVER_IP}:2000/dashboard${NC}"
echo -e "  ${CYAN}3. WAHA Swagger API Docs:${NC}           ${BOLD}http://${SERVER_IP}:2000${NC}"
echo -e "  ${CYAN}4. Contacts Management UI:${NC}          ${BOLD}http://${SERVER_IP}:2001${NC}"
echo -e "  ${CYAN}5. Bot Rules Admin Panel:${NC}           ${BOLD}http://${SERVER_IP}:2003${NC}"
echo ""
echo -e "${BOLD}Credentials:${NC}"
echo -e "  WAHA API Key:             ${YELLOW}${API_KEY}${NC}"
echo -e "  Dashboard Login:          ${YELLOW}${DASH_USER}${NC} / ${YELLOW}${DASH_PASS}${NC}"
echo -e "  Bot Admin Password:       ${YELLOW}${BOT_ADMIN_PASS}${NC}"
echo ""
echo -e "${BOLD}How to Connect WhatsApp via QR Code:${NC}"
echo -e "  ${PURPLE}Option A (Web):${NC}    Open ${BOLD}http://${SERVER_IP}:2000/dashboard${NC} in your browser and click 'Scan QR'."
echo -e "  ${PURPLE}Option B (CLI):${NC}    Run: ${BOLD}docker logs -f waha${NC} to view the ASCII QR code in your terminal."
echo ""
echo -e "${BOLD}Useful Management Commands:${NC}"
echo -e "  View live logs:           ${BOLD}docker compose logs -f${NC}"
echo -e "  Restart all services:     ${BOLD}docker compose restart${NC}"
echo -e "  Stop all services:        ${BOLD}docker compose down${NC}"
echo -e "  Backup full system:       ${BOLD}./backup.sh${NC}"
echo -e "  Restore from backup:      ${BOLD}./restore.sh <backup-file.tar.gz>${NC}"
echo -e "${GREEN}==============================================================${NC}"
