# WhatsApp Bot Flow Builder for WAHA

A visual drag-and-drop WhatsApp chatbot flow builder web application integrated with WAHA (WhatsApp HTTP API).

## Features
- **Visual Canvas Editor**: Drag, drop, and connect nodes with visual bezier wire connectors, pan, and zoom.
- **12 Node Types**:
  1. Incoming Message (Triggers: exact, contains, starts_with, ends_with, regex, any)
  2. Send Text (with variable interpolation e.g. `{{contact.name}}`, `{{message.text}}`, `{{conversation.var}}`)
  3. Condition (YES/NO branching)
  4. Menu / Choice (interactive numbered options routing with fallback)
  5. Wait For Reply (remembers state and resumes flow on response)
  6. Set Variable (stores conversation state in SQLite)
  7. Send Image (URL + caption)
  8. Send File (URL + filename/caption)
  9. Delay (bounded 1-10s delay)
  10. HTTP Request (REST API calls with variable interpolation)
  11. Human Handoff (pauses bot for human agent takeover)
  12. End Flow (marks conversation completed)
- **State Machine**: Tracks conversation state (`idle`, `waiting_for_reply`, `human_mode`, `completed`) in SQLite.
- **Anti-Loop Protection**: Automatically drops `fromMe` messages, filters groups/broadcasts, and caps turns at 50 steps.
- **In-Memory Simulator**: Test flows step-by-step with visual path highlighting.
- **Live WhatsApp Test**: Test flows directly with a live WhatsApp number.
- **Contacts & LID Normalization**: Automatic phone number normalization and LID mapping.
- **Global Bot ON/OFF** & per-contact human takeover controls.
- **Version History & Export/Import**: Export and import flows as JSON.

## Network & Port Map
- **Web UI & REST API**: `http://192.168.100.237:2004`
- **WAHA HTTP API**: `http://localhost:2000` (Internal: `http://waha:3000`)
- **Docker Network**: `waha_default`
- **Database**: `/opt/waha/bot-builder/data/bot.db`

## Management Commands
```bash
cd /opt/waha/bot-builder

# Build and start
docker compose up -d --build

# View logs
docker compose logs -f

# Stop
docker compose down
```
