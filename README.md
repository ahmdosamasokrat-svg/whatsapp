# 🚀 WAHA Suite (WhatsApp API + Visual Flow Builder + Contacts Manager)

A complete, production-ready WhatsApp automation platform built on [WAHA (WhatsApp HTTP API)](https://waha.devlike.pro/). 

Includes:
- **WAHA Core Engine** (NOWEB/GOWS/WEBJS WhatsApp HTTP API, multi-device support)
- **Visual Drag & Drop Flow Builder** (FastAPI backend + canvas editor, 12 node types, SQLite state engine, simulator)
- **Contacts Management UI** (Full contact viewer, LID normalization, manual phone number cleaner)
- **Keyword Rules Bot** (Lightweight regex/keyword autoresponder)
- **Bot Admin Panel** (Web UI for keyword rules management and testing)
- **1-Command Automated Installer** for deploying to any fresh Linux server
- **Automated Backup & Restore** for seamless server-to-server migration

---

## 📐 Architecture & Port Mapping

```
                     +---------------------------------------+
                     |         Docker Host (Server)          |
                     +---------------------------------------+
                                         |
    +-------------------+----------------+-------------------+-------------------+
    |                   |                |                   |                   |
    v                   v                v                   v                   v
[Port 2000]         [Port 2004]      [Port 2001]         [Port 2003]         [Port 2002]
WAHA Core           Flow Builder     Contacts UI         Bot Admin           Simple Bot
(API & Dashboard)   (Visual Studio)  (Contacts Viewer)   (Rules Control)     (Autoresponder)
```

| Service | Port | Description | Auth / Notes |
| :--- | :--- | :--- | :--- |
| **Flow Builder Studio** | `2004` | Visual canvas flow builder & conversation state engine | Direct Web UI & REST API |
| **WAHA Dashboard** | `2000` | Official WAHA UI (`/dashboard`) & Swagger API Docs (`/`) | Basic Auth (configured in `.env`) |
| **Contacts Manager** | `2001` | Contacts list, LID translation & phone normalization | Protected by `WAHA_API_KEY` |
| **Bot Admin Panel** | `2003` | Edit keyword triggers, replies & test message matching | Session Login (`BOT_ADMIN_PASSWORD`) |
| **Keyword Bot** | `2002` | Lightweight Flask webhook autoresponder | Webhook endpoint `/webhook` |

---

## ⚡ Quick 1-Command Install on Any Linux Server

Run this command on your destination server (Ubuntu, Debian, CentOS, Rocky Linux, AlmaLinux):

```bash
curl -fsSL https://raw.githubusercontent.com/ahmdosamasokrat-svg/whatsapp/main/install.sh | bash
```

Or clone and run manually:

```bash
git clone https://github.com/ahmdosamasokrat-svg/whatsapp.git /opt/waha
cd /opt/waha
chmod +x install.sh backup.sh restore.sh
./install.sh
```

### What `install.sh` does automatically:
1. Detects Linux distribution (`apt`, `dnf`, `yum`).
2. Installs dependencies (`curl`, `git`, `jq`, `openssl`, `tar`, `docker`, `docker-compose-plugin`).
3. Generates secure, randomized secrets and passwords in `.env`.
4. Pre-seeds default and custom flows into the SQLite database.
5. Builds and launches all 5 Docker containers.
6. Automatically registers the webhook from WAHA to the Flow Builder.
7. Opens firewall ports (UFW or firewalld) if active.
8. Displays full access URLs, credentials, and QR code instructions.

---

## 📦 How to Push this Project to Your GitHub

Follow these steps on the current server to publish this project to your GitHub account:

### Step 1: Initialize Git & Commit (Clean & Secure)
```bash
cd /opt/waha

# Verify git status
git status

# Add all files (safe: .gitignore automatically excludes secrets, media & session keys)
git add .

# Create initial commit
git commit -m "feat: Initial commit of WAHA suite with automated installer and backup system"
```

### Step 2: Create a New Repository on GitHub
1. Go to [GitHub](https://github.com/new).
2. Create a new repository (e.g. `waha-suite` or `waha-bot`).
3. Choose **Private** (recommended) or **Public**.

### Step 3: Link & Push to GitHub
```bash
cd /opt/waha

# Set default branch
git branch -M main

git remote add origin https://github.com/ahmdosamasokrat-svg/whatsapp.git
# Push to GitHub
git push -u origin main
```

*(Note: Git will ask for your GitHub username and Personal Access Token or SSH key).*

---

## 🔄 Server-to-Server Migration (Transferring Live WhatsApp Sessions)

Because WhatsApp session credentials (`sessions/`) and customer databases (`bot.db`) contain sensitive private data, they are excluded from GitHub for security.

To move your **active WhatsApp connection** and **full database** to the new server without rescanning the QR code:

### On the Current Server:
```bash
cd /opt/waha
./backup.sh
```
This creates a timestamped archive in `/opt/waha/backups/waha-backup-YYYY-MM-DD_HHMMSS.tar.gz`.

### Transfer the Backup to the New Server:
```bash
scp /opt/waha/backups/waha-backup-*.tar.gz user@<NEW_SERVER_IP>:/opt/waha/
```

### On the New Server:
```bash
cd /opt/waha
./restore.sh waha-backup-*.tar.gz
```
The script will restore your `.env`, WhatsApp session tokens, contacts, and database, then automatically restart the containers!

---

## 📱 Connecting WhatsApp (Scan QR Code)

Once installed, connect your WhatsApp number:

### Method 1: Web Dashboard (Easiest)
1. Open `http://<SERVER_IP>:2000/dashboard` in your browser.
2. Log in using `admin` and your `WAHA_DASHBOARD_PASSWORD`.
3. Click on the `test` session.
4. Click **Scan QR** and scan the QR code using WhatsApp on your phone (**Linked Devices** -> **Link a device**).

### Method 2: Terminal Logs
Run in your terminal:
```bash
docker compose logs -f waha
```
WAHA will print the ASCII QR code directly into the terminal. Scan it with your phone!

---

## 🛠️ Management Commands

```bash
cd /opt/waha

# View real-time logs across all services
docker compose logs -f

# View logs for a specific service
docker compose logs -f bot-builder
docker compose logs -f waha

# Restart all services
docker compose restart

# Stop all services
docker compose down

# Rebuild and restart after code changes
docker compose up -d --build
```

---

## 🎨 Visual Flow Builder Highlights

The Flow Builder on port `2004` includes:
- **12 Interactive Node Types**:
  - `Incoming Message` (Triggers: exact, contains, starts_with, regex, any)
  - `Send Text` (Supports variable interpolation `{{contact.name}}`, `{{conversation.var}}`)
  - `Condition` (Branching YES/NO logic)
  - `Menu / Choice` (Interactive numbered options with fallbacks)
  - `Wait For Reply` (State machine waits for user reply)
  - `Set Variable` (Stores conversation state)
  - `Send Image` & `Send File` (Media delivery)
  - `Delay` (Bounded pacing 1-10s)
  - `HTTP Request` (Call external REST APIs with variables)
  - `Human Handoff` (Pause bot and alert human agent)
  - `End Flow`
- **Simulator**: Step-by-step execution in memory with visual path highlighting.
- **Live WhatsApp Test**: Fire test messages to any real WhatsApp number.
- **Anti-Loop Protection**: Drops `fromMe` messages, limits max execution steps to 50, filters broadcasts.
- **Export & Import**: Export flows to JSON and import on any other instance.

---

## 🔒 Security Best Practices

1. Keep `.env` strictly protected (`chmod 600 .env`).
2. Never commit `sessions/` or `bot.db` to a public repository.
3. If exposing ports to the public internet, put them behind Nginx/Caddy with SSL (`certbot`) or a firewall restricting ports to trusted IPs.
