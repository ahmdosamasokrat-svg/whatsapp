import os
import json
import re
from typing import Dict, Any, Optional, List
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from database import get_db, now_iso, init_db
import engine
import waha

app = FastAPI(title="WhatsApp Bot Flow Builder", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
STATIC_DIR = os.path.join(FRONTEND_DIR, "static")

# Mount static files
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.on_event("startup")
def on_startup():
    init_db()


@app.api_route("/", methods=["GET", "HEAD"])
def index():
    index_file = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "WhatsApp Bot Flow Builder Backend Running. Frontend index.html not found."}


@app.api_route("/health", methods=["GET", "HEAD"])
def health():
    return {"status": "ok", "service": "bot-builder"}

# -------------------------------------------------------------
# DASHBOARD API
# -------------------------------------------------------------
@app.get("/api/dashboard")
def get_dashboard():
    conn = get_db()
    try:
        cur = conn.cursor()

        # Flows count
        cur.execute("SELECT COUNT(*) as total, SUM(enabled) as active FROM flows")
        flow_stats = cur.fetchone()

        # Contacts count
        cur.execute("SELECT COUNT(*) as total, SUM(bot_disabled) as bot_disabled FROM contacts")
        contact_stats = cur.fetchone()

        # Conversations
        cur.execute("SELECT COUNT(*) as total, SUM(CASE WHEN status = 'human_mode' THEN 1 ELSE 0 END) as human_mode, SUM(CASE WHEN status = 'waiting_for_reply' THEN 1 ELSE 0 END) as waiting_reply FROM conversations")
        conv_stats = cur.fetchone()

        # Message logs count
        cur.execute("SELECT COUNT(*) as total, SUM(CASE WHEN direction = 'incoming' THEN 1 ELSE 0 END) as incoming, SUM(CASE WHEN direction = 'outgoing' THEN 1 ELSE 0 END) as outgoing FROM message_logs")
        log_stats = cur.fetchone()

        # Recent logs
        cur.execute("SELECT * FROM message_logs ORDER BY id DESC LIMIT 10")
        recent_logs = [dict(r) for r in cur.fetchall()]

        # Global bot status
        bot_enabled = engine.get_setting("bot_enabled", "true").lower() == "true"
        session_name = engine.get_setting("default_session", "test")

        # Check WAHA session info
        session_info = waha.get_session_info(session_name)

        return {
            "bot_enabled": bot_enabled,
            "session_name": session_name,
            "session_status": session_info.get("status") if session_info else "UNKNOWN",
            "flows": {
                "total": flow_stats["total"] or 0,
                "active": flow_stats["active"] or 0
            },
            "contacts": {
                "total": contact_stats["total"] or 0,
                "bot_disabled": contact_stats["bot_disabled"] or 0
            },
            "conversations": {
                "total": conv_stats["total"] or 0,
                "human_mode": conv_stats["human_mode"] or 0,
                "waiting_reply": conv_stats["waiting_reply"] or 0
            },
            "messages": {
                "total": log_stats["total"] or 0,
                "incoming": log_stats["incoming"] or 0,
                "outgoing": log_stats["outgoing"] or 0
            },
            "recent_logs": recent_logs
        }
    finally:
        conn.close()


# -------------------------------------------------------------
# FLOWS API
# -------------------------------------------------------------
class FlowCreateRequest(BaseModel):
    name: str
    description: Optional[str] = ""
    trigger_type: Optional[str] = "contains"
    trigger_value: Optional[str] = ""
    priority: Optional[int] = 100
    is_default: Optional[int] = 0


class FlowUpdateRequest(BaseModel):
    name: str
    description: Optional[str] = ""
    enabled: Optional[int] = 1
    priority: Optional[int] = 100
    is_default: Optional[int] = 0
    trigger_type: Optional[str] = "contains"
    trigger_value: Optional[str] = ""
    nodes_json: Optional[str] = "[]"
    edges_json: Optional[str] = "[]"


@app.get("/api/flows")
def list_flows():
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, name, description, enabled, priority, is_default, trigger_type, trigger_value, version, created_at, updated_at, nodes_json FROM flows ORDER BY priority ASC, id ASC")
        rows = cur.fetchall()
        flows = []
        for r in rows:
            d = dict(r)
            nodes = json.loads(d.pop("nodes_json") or "[]")
            d["node_count"] = len(nodes)
            flows.append(d)
        return flows
    finally:
        conn.close()


@app.post("/api/flows")
def create_flow(req: FlowCreateRequest):
    conn = get_db()
    try:
        cur = conn.cursor()
        now = now_iso()

        # Create basic start node
        initial_nodes = [
            {
                "id": "node_start",
                "type": "start",
                "title": "Incoming Message",
                "position": {"x": 100, "y": 200},
                "data": {
                    "trigger_type": req.trigger_type or "contains",
                    "trigger_value": req.trigger_value or ""
                }
            }
        ]

        cur.execute("""
            INSERT INTO flows (name, description, enabled, priority, is_default, trigger_type, trigger_value, nodes_json, edges_json, version, created_at, updated_at)
            VALUES (?, ?, 1, ?, ?, ?, ?, ?, '[]', 1, ?, ?)
        """, (
            req.name,
            req.description,
            req.priority,
            req.is_default,
            req.trigger_type,
            req.trigger_value,
            json.dumps(initial_nodes, ensure_ascii=False),
            now,
            now
        ))
        flow_id = cur.lastrowid

        # Save initial version
        cur.execute("""
            INSERT INTO flow_versions (flow_id, version, name, description, priority, trigger_type, trigger_value, nodes_json, edges_json, created_at)
            VALUES (?, 1, ?, ?, ?, ?, ?, ?, '[]', ?)
        """, (flow_id, req.name, req.description, req.priority, req.trigger_type, req.trigger_value, json.dumps(initial_nodes, ensure_ascii=False), now))

        conn.commit()
        return {"id": flow_id, "name": req.name, "message": "Flow created successfully"}
    finally:
        conn.close()


@app.get("/api/flows/{flow_id}")
def get_flow(flow_id: int):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM flows WHERE id = ?", (flow_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Flow not found")
        flow = dict(row)
        flow["nodes"] = json.loads(flow.get("nodes_json") or "[]")
        flow["edges"] = json.loads(flow.get("edges_json") or "[]")
        return flow
    finally:
        conn.close()


@app.put("/api/flows/{flow_id}")
def update_flow(flow_id: int, req: FlowUpdateRequest):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT version FROM flows WHERE id = ?", (flow_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Flow not found")

        current_ver = row["version"]
        new_ver = current_ver + 1
        now = now_iso()

        # If this flow is set as default, reset others if needed
        if req.is_default:
            cur.execute("UPDATE flows SET is_default = 0 WHERE id != ?", (flow_id,))
            engine.set_setting("default_flow_id", str(flow_id))

        cur.execute("""
            UPDATE flows SET
                name = ?,
                description = ?,
                enabled = ?,
                priority = ?,
                is_default = ?,
                trigger_type = ?,
                trigger_value = ?,
                nodes_json = ?,
                edges_json = ?,
                version = ?,
                updated_at = ?
            WHERE id = ?
        """, (
            req.name,
            req.description,
            req.enabled,
            req.priority,
            req.is_default,
            req.trigger_type,
            req.trigger_value,
            req.nodes_json,
            req.edges_json,
            new_ver,
            now,
            flow_id
        ))

        # Add version snapshot
        cur.execute("""
            INSERT INTO flow_versions (flow_id, version, name, description, priority, trigger_type, trigger_value, nodes_json, edges_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            flow_id,
            new_ver,
            req.name,
            req.description,
            req.priority,
            req.trigger_type,
            req.trigger_value,
            req.nodes_json,
            req.edges_json,
            now
        ))

        conn.commit()
        return {"id": flow_id, "version": new_ver, "message": "Flow saved successfully"}
    finally:
        conn.close()


@app.delete("/api/flows/{flow_id}")
def delete_flow(flow_id: int):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM flows WHERE id = ?", (flow_id,))
        conn.commit()
        return {"message": f"Flow {flow_id} deleted"}
    finally:
        conn.close()


@app.post("/api/flows/{flow_id}/toggle")
def toggle_flow(flow_id: int):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT enabled FROM flows WHERE id = ?", (flow_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Flow not found")
        new_val = 0 if row["enabled"] else 1
        cur.execute("UPDATE flows SET enabled = ?, updated_at = ? WHERE id = ?", (new_val, now_iso(), flow_id))
        conn.commit()
        return {"id": flow_id, "enabled": new_val}
    finally:
        conn.close()


@app.post("/api/flows/{flow_id}/duplicate")
def duplicate_flow(flow_id: int):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM flows WHERE id = ?", (flow_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Flow not found")
        f = dict(row)
        now = now_iso()
        cur.execute("""
            INSERT INTO flows (name, description, enabled, priority, is_default, trigger_type, trigger_value, nodes_json, edges_json, version, created_at, updated_at)
            VALUES (?, ?, 0, ?, 0, ?, ?, ?, ?, 1, ?, ?)
        """, (
            f"{f['name']} (Copy)",
            f.get("description", ""),
            (f.get("priority") or 100) + 1,
            f.get("trigger_type", "contains"),
            f.get("trigger_value", ""),
            f.get("nodes_json", "[]"),
            f.get("edges_json", "[]"),
            now,
            now
        ))
        new_id = cur.lastrowid
        conn.commit()
        return {"id": new_id, "message": "Flow duplicated successfully"}
    finally:
        conn.close()


@app.get("/api/flows/{flow_id}/export")
def export_flow(flow_id: int):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT name, description, trigger_type, trigger_value, priority, nodes_json, edges_json FROM flows WHERE id = ?", (flow_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Flow not found")
        data = dict(row)
        data["nodes"] = json.loads(data.pop("nodes_json") or "[]")
        data["edges"] = json.loads(data.pop("edges_json") or "[]")
        return data
    finally:
        conn.close()


class FlowImportRequest(BaseModel):
    name: str
    description: Optional[str] = ""
    trigger_type: Optional[str] = "contains"
    trigger_value: Optional[str] = ""
    priority: Optional[int] = 100
    nodes: Optional[List[Dict[str, Any]]] = []
    edges: Optional[List[Dict[str, Any]]] = []


@app.post("/api/flows/import")
def import_flow(req: FlowImportRequest):
    conn = get_db()
    try:
        cur = conn.cursor()
        now = now_iso()
        cur.execute("""
            INSERT INTO flows (name, description, enabled, priority, is_default, trigger_type, trigger_value, nodes_json, edges_json, version, created_at, updated_at)
            VALUES (?, ?, 0, ?, 0, ?, ?, ?, ?, 1, ?, ?)
        """, (
            req.name,
            req.description,
            req.priority,
            req.trigger_type,
            req.trigger_value,
            json.dumps(req.nodes or [], ensure_ascii=False),
            json.dumps(req.edges or [], ensure_ascii=False),
            now,
            now
        ))
        new_id = cur.lastrowid
        conn.commit()
        return {"id": new_id, "message": "Flow imported successfully"}
    finally:
        conn.close()


@app.get("/api/flows/{flow_id}/versions")
def get_flow_versions(flow_id: int):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, version, name, description, priority, created_at FROM flow_versions WHERE flow_id = ? ORDER BY version DESC", (flow_id,))
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


@app.post("/api/flows/{flow_id}/versions/{version}/restore")
def restore_flow_version(flow_id: int, version: int):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM flow_versions WHERE flow_id = ? AND version = ?", (flow_id, version))
        vrow = cur.fetchone()
        if not vrow:
            raise HTTPException(status_code=404, detail="Version not found")
        v = dict(vrow)
        now = now_iso()
        cur.execute("""
            UPDATE flows SET
                name = ?,
                description = ?,
                priority = ?,
                trigger_type = ?,
                trigger_value = ?,
                nodes_json = ?,
                edges_json = ?,
                updated_at = ?
            WHERE id = ?
        """, (
            v["name"],
            v["description"],
            v["priority"],
            v["trigger_type"],
            v["trigger_value"],
            v["nodes_json"],
            v["edges_json"],
            now,
            flow_id
        ))
        conn.commit()
        return {"message": f"Restored version {version}"}
    finally:
        conn.close()


@app.post("/api/flows/{flow_id}/validate")
def validate_flow(flow_id: int):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT nodes_json, edges_json FROM flows WHERE id = ?", (flow_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Flow not found")
        nodes = json.loads(row["nodes_json"] or "[]")
        edges = json.loads(row["edges_json"] or "[]")

        errors = []
        warnings = []

        if not nodes:
            errors.append("Flow has no nodes.")
            return {"valid": False, "errors": errors, "warnings": warnings}

        start_nodes = [n for n in nodes if n.get("type") == "start"]
        if not start_nodes:
            errors.append("Flow must contain at least one Start / Incoming Message node.")

        node_ids = {n.get("id") for n in nodes if n.get("id")}

        # Outgoing edges per node
        outgoing = {}
        for e in edges:
            src = e.get("source")
            outgoing.setdefault(src, []).append(e)

        for n in nodes:
            nid = n.get("id")
            ntype = n.get("type")
            ndata = n.get("data") or {}
            title = n.get("title") or ntype

            if ntype == "send_text":
                if not ndata.get("message", "").strip():
                    warnings.append(f"Node '{title}' has an empty message.")

            elif ntype == "condition":
                yes_edges = [e for e in outgoing.get(nid, []) if e.get("sourceHandle") == "yes"]
                no_edges = [e for e in outgoing.get(nid, []) if e.get("sourceHandle") == "no"]
                if not yes_edges:
                    warnings.append(f"Condition node '{title}' has no YES output connected.")
                if not no_edges:
                    warnings.append(f"Condition node '{title}' has no NO output connected.")

            elif ntype == "menu":
                opts = ndata.get("options") or []
                if not opts:
                    errors.append(f"Menu node '{title}' has no choices/options defined.")
                otherwise_edges = [e for e in outgoing.get(nid, []) if e.get("sourceHandle") == "otherwise"]
                if not otherwise_edges:
                    warnings.append(f"Menu node '{title}' has no 'otherwise' fallback branch connected.")

            elif ntype == "send_image":
                if not ndata.get("image_url", "").strip():
                    warnings.append(f"Send Image node '{title}' has no Image URL.")

            elif ntype == "send_file":
                if not ndata.get("file_url", "").strip():
                    warnings.append(f"Send File node '{title}' has no File URL.")

            elif ntype == "http_request":
                if not ndata.get("url", "").strip():
                    errors.append(f"HTTP Request node '{title}' is missing a URL.")

            # Check if node has disconnected outgoing path (except end, human_handoff, wait_for_reply, menu)
            if ntype not in ["end", "human_handoff", "menu", "condition"]:
                if nid not in outgoing:
                    warnings.append(f"Node '{title}' has no outgoing connections.")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings
        }
    finally:
        conn.close()


class FlowTestRequest(BaseModel):
    message: str
    resume_node_id: Optional[str] = None
    contact_name: Optional[str] = "Ahmed"
    contact_number: Optional[str] = "201281102350"
    variables: Optional[Dict[str, Any]] = {}


@app.post("/api/flows/{flow_id}/test")
async def test_flow_simulation(flow_id: int, req: FlowTestRequest):
    conn = get_db()
    flow = None
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM flows WHERE id = ?", (flow_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Flow not found")
        flow = dict(row)
    finally:
        conn.close()

    contact = {
        "id": req.contact_number,
        "name": req.contact_name,
        "push_name": req.contact_name,
        "variables": req.variables or {}
    }

    result = await engine.execute_flow_step(
        flow=flow,
        contact=contact,
        incoming_text=req.message,
        resume_node_id=req.resume_node_id,
        is_simulation=True
    )

    return result


class LiveTestRequest(BaseModel):
    number: str
    message: str


@app.post("/api/flows/{flow_id}/live-test")
async def live_test_flow(flow_id: int, req: LiveTestRequest):
    clean_num = waha.clean_phone_number(req.number)
    if not clean_num:
        raise HTTPException(status_code=400, detail="Invalid WhatsApp phone number.")

    # Call incoming message processing using the target number
    result = await engine.process_incoming_message(
        contact_id=clean_num,
        message_text=req.message,
        sender_name="Live Tester",
        push_name="Live Tester"
    )

    return {"status": "sent", "contact_id": clean_num, "result": result}


# -------------------------------------------------------------
# CONTACTS API
# -------------------------------------------------------------
@app.get("/api/contacts")
def list_contacts(q: Optional[str] = None, limit: int = 100, offset: int = 0):
    conn = get_db()
    try:
        cur = conn.cursor()
        if q:
            term = f"%{q}%"
            cur.execute("""
                SELECT * FROM contacts
                WHERE id LIKE ? OR name LIKE ? OR push_name LIKE ? OR lid LIKE ?
                ORDER BY last_seen DESC
                LIMIT ? OFFSET ?
            """, (term, term, term, term, limit, offset))
        else:
            cur.execute("SELECT * FROM contacts ORDER BY last_seen DESC LIMIT ? OFFSET ?", (limit, offset))
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


@app.put("/api/contacts/{contact_id}/toggle-bot")
def toggle_contact_bot(contact_id: str):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT bot_disabled FROM contacts WHERE id = ?", (contact_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Contact not found")
        new_val = 0 if row["bot_disabled"] else 1
        cur.execute("UPDATE contacts SET bot_disabled = ? WHERE id = ?", (new_val, contact_id))

        # If bot is re-enabled, also update conversation state if in human_mode
        if new_val == 0:
            cur.execute("UPDATE conversations SET status = 'idle' WHERE contact_id = ? AND status = 'human_mode'", (contact_id,))

        conn.commit()
        return {"contact_id": contact_id, "bot_disabled": new_val}
    finally:
        conn.close()


@app.post("/api/contacts/sync")
def sync_contacts(background_tasks: BackgroundTasks):
    def run_sync():
        session_name = engine.get_setting("default_session", "test")
        waha_contacts = waha.get_all_contacts(session_name)
        lid_map = waha.get_lid_map(session_name)
        now = now_iso()

        conn = get_db()
        try:
            cur = conn.cursor()
            for c in waha_contacts:
                cid = c.get("id", "")
                if cid.endswith("@g.us") or cid.endswith("@broadcast") or cid == "status@broadcast":
                    continue

                name = c.get("name") or c.get("pushname") or c.get("shortName") or ""
                phone = waha.clean_phone_number(c.get("phoneNumber") or c.get("number"))
                lid = c.get("lid")

                if not phone and lid:
                    phone = lid_map.get(lid, "")
                if not phone and cid.endswith("@lid"):
                    phone = lid_map.get(cid, "")
                if not phone and (cid.endswith("@c.us") or cid.endswith("@s.whatsapp.net")):
                    phone = waha.clean_phone_number(cid)

                if not phone:
                    continue

                cur.execute("""
                    INSERT INTO contacts (id, name, push_name, lid, bot_disabled, last_seen)
                    VALUES (?, ?, ?, ?, 0, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        name = COALESCE(excluded.name, contacts.name),
                        push_name = COALESCE(excluded.push_name, contacts.push_name),
                        lid = COALESCE(excluded.lid, contacts.lid)
                """, (phone, name or "Friend", name or "Friend", lid or "", now))
            conn.commit()
        finally:
            conn.close()

    background_tasks.add_task(run_sync)
    return {"message": "Sync started in background"}


# -------------------------------------------------------------
# CONVERSATIONS API
# -------------------------------------------------------------
@app.get("/api/conversations")
def list_conversations(status: Optional[str] = None):
    conn = get_db()
    try:
        cur = conn.cursor()
        query = """
            SELECT c.*, ct.name as contact_name, ct.push_name, ct.bot_disabled, f.name as flow_name
            FROM conversations c
            LEFT JOIN contacts ct ON c.contact_id = ct.id
            LEFT JOIN flows f ON c.flow_id = f.id
        """
        params = []
        if status:
            query += " WHERE c.status = ?"
            params.append(status)
        query += " ORDER BY c.updated_at DESC LIMIT 100"

        cur.execute(query, tuple(params))
        rows = cur.fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["variables"] = engine.get_contact_variables(d["contact_id"])
            result.append(d)
        return result
    finally:
        conn.close()


@app.get("/api/conversations/{contact_id}")
def get_conversation_history(contact_id: str):
    conn = get_db()
    try:
        cur = conn.cursor()
        # Contact info
        cur.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,))
        contact = cur.fetchone()

        # Conversation state
        cur.execute("SELECT * FROM conversations WHERE contact_id = ?", (contact_id,))
        conv = cur.fetchone()

        # Variables
        cur.execute("SELECT key, value FROM conversation_variables WHERE contact_id = ?", (contact_id,))
        variables = {r["key"]: r["value"] for r in cur.fetchall()}

        # Logs / chat history
        cur.execute("""
            SELECT * FROM message_logs
            WHERE contact_id = ?
            ORDER BY id ASC
            LIMIT 200
        """, (contact_id,))
        logs = [dict(r) for r in cur.fetchall()]

        return {
            "contact": dict(contact) if contact else {"id": contact_id},
            "conversation": dict(conv) if conv else None,
            "variables": variables,
            "history": logs
        }
    finally:
        conn.close()


class AgentReplyRequest(BaseModel):
    message: str


@app.post("/api/conversations/{contact_id}/send")
def send_agent_reply(contact_id: str, req: AgentReplyRequest):
    message_text = (req.message or "").strip()
    if not message_text:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    clean_id = waha.clean_phone_number(contact_id)
    if not clean_id:
        raise HTTPException(status_code=400, detail="Invalid contact ID")

    session_name = engine.get_setting("default_session", "test")

    # 1. Send text message via WAHA to customer WhatsApp
    try:
        waha.send_text(clean_id, message_text, session=session_name)
    except Exception as e:
        engine.log_event("error", "agent_send_error", clean_id, None, None, f"Error sending message: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to send message via WhatsApp: {e}")

    # 2. Log outgoing message
    engine.log_event(
        direction="outgoing",
        event_type="agent_reply",
        contact_id=clean_id,
        flow_id=None,
        node_id=None,
        message_text=message_text,
        details={"sender": "human_agent"}
    )

    # 3. Automatically pause bot for this contact (human takeover mode)
    conn = get_db()
    now = now_iso()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE contacts SET bot_disabled = 1, last_seen = ? WHERE id = ?", (now, clean_id))
        cur.execute("""
            INSERT INTO conversations (contact_id, status, last_message_at, updated_at)
            VALUES (?, 'human_mode', ?, ?)
            ON CONFLICT(contact_id) DO UPDATE SET
                status = 'human_mode',
                last_message_at = excluded.last_message_at,
                updated_at = excluded.updated_at
        """, (clean_id, now, now))
        conn.commit()
    finally:
        conn.close()

    return {
        "success": True,
        "contact_id": clean_id,
        "message": message_text,
        "status": "human_mode"
    }

@app.post("/api/conversations/{contact_id}/resume")
def resume_bot_for_contact(contact_id: str):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE contacts SET bot_disabled = 0 WHERE id = ?", (contact_id,))
        cur.execute("UPDATE conversations SET status = 'idle', current_node_id = NULL WHERE contact_id = ?", (contact_id,))
        conn.commit()

        engine.log_event(
            direction="system",
            event_type="bot_resumed",
            contact_id=contact_id,
            message_text="Admin resumed bot automation"
        )
        return {"contact_id": contact_id, "status": "idle", "bot_disabled": 0}
    finally:
        conn.close()


@app.post("/api/conversations/{contact_id}/reset")
def reset_conversation(contact_id: str):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE conversations SET status = 'idle', flow_id = NULL, current_node_id = NULL WHERE contact_id = ?", (contact_id,))
        conn.commit()
        return {"contact_id": contact_id, "status": "idle"}
    finally:
        conn.close()


# -------------------------------------------------------------
# LOGS API
# -------------------------------------------------------------
@app.get("/api/logs")
def get_logs(
    direction: Optional[str] = None,
    event_type: Optional[str] = None,
    contact_id: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
):
    conn = get_db()
    try:
        cur = conn.cursor()
        clauses = []
        params = []

        if direction:
            clauses.append("direction = ?")
            params.append(direction)
        if event_type:
            clauses.append("event_type = ?")
            params.append(event_type)
        if contact_id:
            clauses.append("contact_id = ?")
            params.append(contact_id)

        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        query = f"SELECT * FROM message_logs {where} ORDER BY id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cur.execute(query, tuple(params))
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


@app.delete("/api/logs")
def clear_logs():
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM message_logs")
        conn.commit()
        return {"message": "Logs cleared successfully"}
    finally:
        conn.close()


# -------------------------------------------------------------
# SETTINGS API
# -------------------------------------------------------------
@app.get("/api/settings")
def get_settings():
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT key, value FROM bot_settings")
        settings = {r["key"]: r["value"] for r in cur.fetchall()}

        # WAHA details
        session_name = settings.get("default_session", "test")
        session_info = waha.get_session_info(session_name)

        return {
            "settings": settings,
            "waha_url": waha.WAHA_URL,
            "session_name": session_name,
            "session_status": session_info.get("status") if session_info else "UNKNOWN",
            "has_api_key": bool(waha.WAHA_API_KEY)
        }
    finally:
        conn.close()


@app.put("/api/settings")
def update_settings(data: Dict[str, Any]):
    conn = get_db()
    try:
        cur = conn.cursor()
        for k, v in data.items():
            cur.execute("INSERT OR REPLACE INTO bot_settings (key, value) VALUES (?, ?)", (k, str(v)))
        conn.commit()
        return {"message": "Settings updated successfully"}
    finally:
        conn.close()


# -------------------------------------------------------------
# WAHA WEBHOOK ENDPOINT
# -------------------------------------------------------------
@app.post("/webhook/waha")
async def waha_webhook(request: Request):
    data = await request.json() or {}

    event = data.get("event")
    if event != "message":
        return JSONResponse({"ignored": "not-message-event", "event": event})

    payload = data.get("payload") or {}

    # ANTI-LOOP 1: Never answer our own messages
    if payload.get("fromMe"):
        return JSONResponse({"ignored": "fromMe"})

    chat_id = payload.get("chatId") or payload.get("from") or ""
    if not chat_id:
        return JSONResponse({"ignored": "no-chatId"})

    # Always ignore newsletters and status broadcasts
    if (
        chat_id.endswith("@newsletter")
        or chat_id.endswith("@broadcast")
        or chat_id == "status@broadcast"
    ):
        return JSONResponse({"ignored": "broadcast-or-newsletter"})

    session_name = data.get("session") or engine.get_setting("default_session", "test")
    is_group = chat_id.endswith("@g.us")

    raw_body = (payload.get("body") or "").strip()
    sender_name = payload.get("_data", {}).get("notifyName") or payload.get("pushName") or ""
    push_name = payload.get("pushName") or sender_name
    lid = payload.get("lid") or ""

    if is_group:
        group_mode = engine.get_setting("group_mode", "mentions_only").lower()
        if group_mode == "disabled":
            return JSONResponse({"ignored": "group-messages-disabled"})

        if group_mode == "mentions_only":
            my_info = waha.get_my_info(session_name)
            my_id = my_info.get("id", "")
            my_num = my_info.get("number", "")
            my_lid = my_info.get("lid", "")
            my_name = my_info.get("pushName", "")

            mentioned_ids = (
                payload.get("mentionedIds")
                or payload.get("_data", {}).get("mentionedJidList")
                or []
            )

            is_mentioned = False
            if my_id and any(m == my_id for m in mentioned_ids):
                is_mentioned = True
            elif my_num and any(my_num in str(m) for m in mentioned_ids):
                is_mentioned = True
            elif my_lid and any(my_lid in str(m) for m in mentioned_ids):
                is_mentioned = True
            elif my_num and (f"@{my_num}" in raw_body or re.search(rf"@\+?{my_num}\b", raw_body)):
                is_mentioned = True
            elif my_name and f"@{my_name.lower()}" in raw_body.lower():
                is_mentioned = True
            elif "@" in raw_body and any(my_num and my_num in str(m) for m in mentioned_ids):
                is_mentioned = True

            if not is_mentioned:
                return JSONResponse({"ignored": "group-bot-not-mentioned"})

            # Strip mention tag from message so triggers match cleanly
            cleaned_text = raw_body
            if my_num:
                cleaned_text = re.sub(rf"@\+?{my_num}\b", "", cleaned_text, flags=re.IGNORECASE)
            if my_name:
                cleaned_text = re.sub(rf"@{re.escape(my_name)}\b", "", cleaned_text, flags=re.IGNORECASE)
            cleaned_text = re.sub(r"^@\S+\s*", "", cleaned_text.strip())
            message_text = cleaned_text.strip()
        else:
            message_text = raw_body

        target_contact_id = chat_id
        group_name = payload.get("_data", {}).get("chat", {}).get("name") or "WhatsApp Group"
        sender_display = f"{sender_name} ({group_name})" if sender_name else group_name

    else:
        message_text = raw_body
        clean_number = waha.clean_phone_number(chat_id)
        if not clean_number or chat_id.endswith("@lid"):
            lid_map = waha.get_lid_map(session_name)
            if lid and lid in lid_map:
                clean_number = lid_map[lid]
            elif chat_id in lid_map:
                clean_number = lid_map[chat_id]

        if not clean_number:
            return JSONResponse({"ignored": "unresolved-contact-number"})

        target_contact_id = clean_number
        sender_display = sender_name

    # Process message in flow execution engine
    result = await engine.process_incoming_message(
        contact_id=target_contact_id,
        message_text=message_text,
        sender_name=sender_display,
        push_name=push_name,
        lid=lid
    )

    return JSONResponse({
        "status": "processed",
        "contact": target_contact_id,
        "is_group": is_group,
        "result": result
    })
