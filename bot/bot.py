import os
import json
import requests

from flask import Flask, request, jsonify

app = Flask(__name__)

WAHA_URL = os.environ.get("WAHA_URL", "http://waha:3000")
WAHA_API_KEY = os.environ.get("WAHA_API_KEY", "")
DEFAULT_SESSION = os.environ.get("WAHA_SESSION", "test")

RULES_FILE = "/app/rules.json"


def load_rules():
    try:
        with open(RULES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print("RULE ERROR:", e, flush=True)
        return {"exact": {}, "contains": {}}


def find_reply(message):
    text = (message or "").strip().lower()

    if not text:
        return None

    rules = load_rules()

    # Exact matches
    for trigger, reply in rules.get("exact", {}).items():
        if text == trigger.strip().lower():
            return reply

    # Contains matches
    for trigger, reply in rules.get("contains", {}).items():
        if trigger.strip().lower() in text:
            return reply

    return None


def normalize_chat_id(chat_id):
    if not chat_id:
        return None

    # NOWEB can occasionally expose this format internally.
    if chat_id.endswith("@s.whatsapp.net"):
        return chat_id.replace("@s.whatsapp.net", "@c.us")

    return chat_id


def send_message(session, chat_id, text):
    headers = {"Content-Type": "application/json"}
    if WAHA_API_KEY:
        headers["X-Api-Key"] = WAHA_API_KEY
    response = requests.post(
        f"{WAHA_URL}/api/sendText",
        headers=headers,
        json={
            "session": session,
            "chatId": chat_id,
            "text": text
        },
        timeout=30
    )
    response.raise_for_status()

    return response.json()


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok"
    })


@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(silent=True) or {}

    if data.get("event") != "message":
        return jsonify({"ignored": "not-message"})

    payload = data.get("payload") or {}

    # Never answer our own messages
    if payload.get("fromMe"):
        return jsonify({"ignored": "fromMe"})

    message = payload.get("body", "")

    # Prefer WAHA's chatId for incoming conversations
    chat_id = (
        payload.get("chatId")
        or payload.get("from")
    )

    chat_id = normalize_chat_id(chat_id)

    if not chat_id:
        return jsonify({"ignored": "no-chat-id"})

    # Ignore groups, channels and status
    if (
        chat_id.endswith("@g.us")
        or chat_id.endswith("@newsletter")
        or chat_id.endswith("@broadcast")
    ):
        return jsonify({"ignored": "non-private-chat"})

    reply = find_reply(message)

    print(
        f"INCOMING chat={chat_id} text={message!r}",
        flush=True
    )

    if not reply:
        print("NO MATCH", flush=True)
        return jsonify({"matched": False})

    session = data.get("session") or DEFAULT_SESSION

    try:
        result = send_message(
            session,
            chat_id,
            reply
        )

        print(
            f"REPLIED chat={chat_id} reply={reply!r}",
            flush=True
        )

        return jsonify({
            "matched": True,
            "reply": reply,
            "result": result
        })

    except Exception as e:
        print(
            f"SEND ERROR: {e}",
            flush=True
        )

        return jsonify({
            "error": str(e)
        }), 500


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=2002
    )
