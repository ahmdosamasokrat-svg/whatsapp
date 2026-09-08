import os
import re
import requests
from typing import Dict, Any, Optional, List

WAHA_URL = os.environ.get("WAHA_URL", "http://waha:3000")
WAHA_API_KEY = os.environ.get("WAHA_API_KEY", "")
DEFAULT_SESSION = os.environ.get("WAHA_SESSION", "test")

# Fallback: if WAHA_API_KEY is not set in environment, search for .env
if not WAHA_API_KEY:
    env_candidates = [
        os.environ.get("ENV_FILE", ""),
        os.path.join(os.path.dirname(__file__), "..", "..", ".env"),
        os.path.join(os.path.dirname(__file__), "..", ".env"),
        ".env",
        "/opt/waha/.env"
    ]
    for cand in env_candidates:
        if cand and os.path.exists(cand):
            try:
                with open(cand, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("WAHA_API_KEY="):
                            WAHA_API_KEY = line.split("=", 1)[1].strip().strip('"').strip("'")
                            break
                if WAHA_API_KEY:
                    break
            except Exception:
                pass


def get_headers() -> Dict[str, str]:
    headers = {
        "Content-Type": "application/json"
    }
    if WAHA_API_KEY:
        headers["X-Api-Key"] = WAHA_API_KEY
    return headers


def clean_phone_number(value: Any) -> str:
    if not value:
        return ""
    val_str = str(value).strip()
    for suffix in ["@s.whatsapp.net", "@c.us", "@lid", "@g.us", "@broadcast", "@newsletter"]:
        if val_str.endswith(suffix):
            val_str = val_str[:-len(suffix)]
    # Keep only digits and plus
    return re.sub(r"[^\d+]", "", val_str)


def format_chat_id(number: str) -> str:
    num_str = str(number).strip()
    if num_str.endswith("@g.us"):
        return num_str
    cleaned = clean_phone_number(num_str)
    # Remove leading plus for WAHA chatId standard
    digits = cleaned.lstrip("+")
    return f"{digits}@c.us"

def send_text(chat_id: str, text: str, session: Optional[str] = None) -> Dict[str, Any]:
    sess = session or DEFAULT_SESSION
    formatted_id = format_chat_id(chat_id)
    url = f"{WAHA_URL}/api/sendText"
    body = {
        "session": sess,
        "chatId": formatted_id,
        "text": text
    }
    resp = requests.post(url, headers=get_headers(), json=body, timeout=30)
    resp.raise_for_status()
    return resp.json() if resp.content else {"success": True}


def send_image(chat_id: str, image_url: str, caption: Optional[str] = None, session: Optional[str] = None) -> Dict[str, Any]:
    sess = session or DEFAULT_SESSION
    formatted_id = format_chat_id(chat_id)
    url = f"{WAHA_URL}/api/sendImage"
    body = {
        "session": sess,
        "chatId": formatted_id,
        "file": {
            "url": image_url
        }
    }
    if caption:
        body["caption"] = caption
    resp = requests.post(url, headers=get_headers(), json=body, timeout=45)
    resp.raise_for_status()
    return resp.json() if resp.content else {"success": True}


def send_file(chat_id: str, file_url: str, filename: Optional[str] = None, caption: Optional[str] = None, session: Optional[str] = None) -> Dict[str, Any]:
    sess = session or DEFAULT_SESSION
    formatted_id = format_chat_id(chat_id)
    url = f"{WAHA_URL}/api/sendFile"
    file_obj: Dict[str, Any] = {"url": file_url}
    if filename:
        file_obj["filename"] = filename
    body = {
        "session": sess,
        "chatId": formatted_id,
        "file": file_obj
    }
    if caption:
        body["caption"] = caption
    resp = requests.post(url, headers=get_headers(), json=body, timeout=45)
    resp.raise_for_status()
    return resp.json() if resp.content else {"success": True}


def get_lid_map(session: Optional[str] = None) -> Dict[str, str]:
    sess = session or DEFAULT_SESSION
    mappings: Dict[str, str] = {}
    limit = 500
    offset = 0

    while True:
        try:
            resp = requests.get(
                f"{WAHA_URL}/api/{sess}/lids",
                headers=get_headers(),
                params={"limit": limit, "offset": offset},
                timeout=30
            )
            if not resp.ok:
                break
            batch = resp.json()
            if not isinstance(batch, list) or len(batch) == 0:
                break
            for item in batch:
                lid = item.get("lid")
                pn = item.get("pn")
                if lid and pn:
                    mappings[lid] = clean_phone_number(pn)
            if len(batch) < limit:
                break
            offset += limit
        except Exception:
            break

    return mappings


def get_all_contacts(session: Optional[str] = None) -> List[Dict[str, Any]]:
    sess = session or DEFAULT_SESSION
    contacts: List[Dict[str, Any]] = []
    limit = 500
    offset = 0

    while True:
        try:
            resp = requests.get(
                f"{WAHA_URL}/api/contacts/all",
                headers=get_headers(),
                params={"session": sess, "limit": limit, "offset": offset},
                timeout=45
            )
            if not resp.ok:
                break
            batch = resp.json()
            if not isinstance(batch, list) or len(batch) == 0:
                break
            contacts.extend(batch)
            if len(batch) < limit:
                break
            offset += limit
        except Exception:
            break

    return contacts


def get_session_info(session: Optional[str] = None) -> Optional[Dict[str, Any]]:
    sess = session or DEFAULT_SESSION
    try:
        resp = requests.get(f"{WAHA_URL}/api/sessions", headers=get_headers(), timeout=15)
        if resp.ok:
            sessions = resp.json()
            if isinstance(sessions, list):
                for s in sessions:
                    if s.get("name") == sess:
                        return s
    except Exception:
        pass
    return None


_MY_INFO_CACHE: Dict[str, Dict[str, str]] = {}

def get_my_info(session: Optional[str] = None) -> Dict[str, str]:
    sess = session or DEFAULT_SESSION
    if sess in _MY_INFO_CACHE and _MY_INFO_CACHE[sess].get("id"):
        return _MY_INFO_CACHE[sess]
    s_info = get_session_info(sess)
    if s_info and s_info.get("me"):
        me = s_info["me"]
        info = {
            "id": me.get("id", ""),
            "number": clean_phone_number(me.get("id", "")),
            "lid": me.get("lid", ""),
            "pushName": me.get("pushName", "")
        }
        _MY_INFO_CACHE[sess] = info
        return info
    return {"id": "", "number": "", "lid": "", "pushName": ""}

def set_session_webhook(session: Optional[str] = None, webhook_url: str = "") -> bool:
    sess = session or DEFAULT_SESSION
    url = f"{WAHA_URL}/api/sessions/{sess}"
    body = {
        "config": {
            "webhooks": [
                {
                    "url": webhook_url,
                    "events": ["message"]
                }
            ]
        }
    }
    try:
        resp = requests.patch(url, headers=get_headers(), json=body, timeout=15)
        return resp.ok
    except Exception:
        return False
