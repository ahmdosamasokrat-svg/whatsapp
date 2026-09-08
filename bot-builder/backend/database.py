import os
import sqlite3
import json
from datetime import datetime

DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "..", "data", "bot.db"))


def get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def now_iso():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def init_db():
    conn = get_db()
    cur = conn.cursor()

    # 1. Bot settings table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS bot_settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    """)

    # 2. Flows table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS flows (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT,
        enabled INTEGER NOT NULL DEFAULT 1,
        priority INTEGER NOT NULL DEFAULT 100,
        is_default INTEGER NOT NULL DEFAULT 0,
        trigger_type TEXT NOT NULL DEFAULT 'contains',
        trigger_value TEXT NOT NULL DEFAULT '',
        nodes_json TEXT NOT NULL DEFAULT '[]',
        edges_json TEXT NOT NULL DEFAULT '[]',
        version INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """)

    # 3. Flow versions history
    cur.execute("""
    CREATE TABLE IF NOT EXISTS flow_versions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        flow_id INTEGER NOT NULL,
        version INTEGER NOT NULL,
        name TEXT NOT NULL,
        description TEXT,
        priority INTEGER NOT NULL,
        trigger_type TEXT NOT NULL,
        trigger_value TEXT NOT NULL,
        nodes_json TEXT NOT NULL,
        edges_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (flow_id) REFERENCES flows(id) ON DELETE CASCADE
    );
    """)

    # 4. Contacts table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS contacts (
        id TEXT PRIMARY KEY,
        name TEXT,
        push_name TEXT,
        lid TEXT,
        bot_disabled INTEGER NOT NULL DEFAULT 0,
        last_seen TEXT NOT NULL
    );
    """)

    # 5. Conversations state table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS conversations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        contact_id TEXT NOT NULL UNIQUE,
        flow_id INTEGER,
        current_node_id TEXT,
        status TEXT NOT NULL DEFAULT 'idle',
        last_message_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (contact_id) REFERENCES contacts(id) ON DELETE CASCADE
    );
    """)

    # 6. Conversation variables table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS conversation_variables (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        contact_id TEXT NOT NULL,
        key TEXT NOT NULL,
        value TEXT,
        updated_at TEXT NOT NULL,
        UNIQUE(contact_id, key),
        FOREIGN KEY (contact_id) REFERENCES contacts(id) ON DELETE CASCADE
    );
    """)

    # 7. Message and event logs table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS message_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        direction TEXT NOT NULL,
        contact_id TEXT,
        flow_id INTEGER,
        node_id TEXT,
        event_type TEXT NOT NULL,
        message_text TEXT,
        details TEXT
    );
    """)

    # Indices for performance
    cur.execute("CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON message_logs(timestamp DESC);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_logs_contact ON message_logs(contact_id);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_conversations_contact ON conversations(contact_id);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_flows_priority ON flows(priority ASC);")

    # Initial settings
    default_settings = {
        "bot_enabled": "true",
        "default_session": "test",
        "max_execution_steps": "50",
        "ignore_groups": "true",
        "default_flow_id": ""
    }
    for k, v in default_settings.items():
        cur.execute("INSERT OR IGNORE INTO bot_settings (key, value) VALUES (?, ?)", (k, v))

    conn.commit()

    # Seed default sample flow if empty
    cur.execute("SELECT COUNT(*) as count FROM flows")
    if cur.fetchone()["count"] == 0:
        seed_sample_flows(conn)

    conn.close()


def seed_sample_flows(conn):
    cur = conn.cursor()
    now = now_iso()

    # First check if flows_export.json exists to load pre-configured flows
    seed_candidates = [
        os.path.join(os.path.dirname(__file__), "..", "data", "flows_export.json"),
        os.path.join(os.path.dirname(__file__), "flows_export.json"),
        "/app/data/flows_export.json"
    ]
    for cand in seed_candidates:
        if os.path.exists(cand):
            try:
                with open(cand, "r", encoding="utf-8") as f:
                    flows_list = json.load(f)
                if isinstance(flows_list, list) and len(flows_list) > 0:
                    for fl in flows_list:
                        cur.execute("""
                        INSERT INTO flows (name, description, enabled, priority, is_default, trigger_type, trigger_value, nodes_json, edges_json, version, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            fl.get("name", "Flow"),
                            fl.get("description", ""),
                            1 if fl.get("enabled", True) else 0,
                            fl.get("priority", 100),
                            1 if fl.get("is_default", False) else 0,
                            fl.get("trigger_type", "contains"),
                            fl.get("trigger_value", ""),
                            json.dumps(fl.get("nodes", []), ensure_ascii=False),
                            json.dumps(fl.get("edges", []), ensure_ascii=False),
                            fl.get("version", 1),
                            now,
                            now
                        ))
                        fid = cur.lastrowid
                        if fl.get("is_default"):
                            cur.execute("UPDATE bot_settings SET value = ? WHERE key = 'default_flow_id'", (str(fid),))
                    conn.commit()
                    return
            except Exception as e:
                print(f"Failed loading seed flows from {cand}: {e}", flush=True)

    # Fallback to built-in default flows if seed file is unavailable
    # 1. Main Welcome Flow
    welcome_nodes = [
        {
            "id": "node_1",
            "type": "start",
            "title": "Incoming Message",
            "position": {"x": 100, "y": 200},
            "data": {
                "trigger_type": "contains",
                "trigger_value": "hello,hi,مرحبا,السلام"
            }
        },
        {
            "id": "node_2",
            "type": "send_text",
            "title": "Welcome Greeting",
            "position": {"x": 380, "y": 200},
            "data": {
                "message": "Welcome to Sokrat Tech 👋\nHow can we help you today?"
            }
        },
        {
            "id": "node_3",
            "type": "menu",
            "title": "Main Menu Options",
            "position": {"x": 660, "y": 200},
            "data": {
                "message": "Please choose:\n\n1 - Sales\n2 - Technical Support\n3 - Location",
                "options": [
                    {"id": "opt_1", "label": "1 - Sales", "value": "1", "pattern": "1|sales|مبيعات"},
                    {"id": "opt_2", "label": "2 - Technical Support", "value": "2", "pattern": "2|support|دعم|صيانة"},
                    {"id": "opt_3", "label": "3 - Location", "value": "3", "pattern": "3|location|موقع|عنوان"}
                ]
            }
        },
        {
            "id": "node_4",
            "type": "send_text",
            "title": "Sales Question",
            "position": {"x": 1000, "y": 80},
            "data": {
                "message": "Please tell us what product or service you are interested in."
            }
        },
        {
            "id": "node_5",
            "type": "human_handoff",
            "title": "Transfer to Sales Team",
            "position": {"x": 1280, "y": 80},
            "data": {
                "notify_message": "Transferred to human sales agent."
            }
        },
        {
            "id": "node_6",
            "type": "send_text",
            "title": "Support Question",
            "position": {"x": 1000, "y": 220},
            "data": {
                "message": "Please describe your technical problem or question."
            }
        },
        {
            "id": "node_7",
            "type": "wait_for_reply",
            "title": "Wait for Problem Description",
            "position": {"x": 1280, "y": 220},
            "data": {
                "variable_name": "problem_description"
            }
        },
        {
            "id": "node_8",
            "type": "send_text",
            "title": "Support Confirmation",
            "position": {"x": 1560, "y": 220},
            "data": {
                "message": "Thank you {{contact.name}}! Our support team has logged your issue: \"{{conversation.problem_description}}\" and will respond shortly."
            }
        },
        {
            "id": "node_9",
            "type": "send_text",
            "title": "Location Info",
            "position": {"x": 1000, "y": 380},
            "data": {
                "message": "📍 Our Location:\nBuilding 14, Tech Park, Cairo, Egypt\nWorking Hours: Sun-Thu 9:00 AM - 5:00 PM"
            }
        },
        {
            "id": "node_10",
            "type": "end",
            "title": "End Conversation",
            "position": {"x": 1280, "y": 380},
            "data": {}
        },
        {
            "id": "node_11",
            "type": "send_text",
            "title": "Invalid Selection",
            "position": {"x": 1000, "y": 520},
            "data": {
                "message": "Invalid option. Please choose 1, 2, or 3."
            }
        }
    ]

    welcome_edges = [
        {"id": "e_1_2", "source": "node_1", "target": "node_2"},
        {"id": "e_2_3", "source": "node_2", "target": "node_3"},
        {"id": "e_3_opt_1", "source": "node_3", "sourceHandle": "opt_1", "target": "node_4"},
        {"id": "e_4_5", "source": "node_4", "target": "node_5"},
        {"id": "e_3_opt_2", "source": "node_3", "sourceHandle": "opt_2", "target": "node_6"},
        {"id": "e_6_7", "source": "node_6", "target": "node_7"},
        {"id": "e_7_8", "source": "node_7", "target": "node_8"},
        {"id": "e_3_opt_3", "source": "node_3", "sourceHandle": "opt_3", "target": "node_9"},
        {"id": "e_9_10", "source": "node_9", "target": "node_10"},
        {"id": "e_3_fallback", "source": "node_3", "sourceHandle": "otherwise", "target": "node_11"}
    ]

    cur.execute("""
    INSERT INTO flows (name, description, enabled, priority, is_default, trigger_type, trigger_value, nodes_json, edges_json, version, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        "Main Welcome Flow",
        "Greeting flow with interactive menu for Sales, Technical Support, and Location",
        1,
        10,
        0,
        "contains",
        "hello,hi,مرحبا,السلام",
        json.dumps(welcome_nodes, ensure_ascii=False),
        json.dumps(welcome_edges, ensure_ascii=False),
        1,
        now,
        now
    ))
    flow_id = cur.lastrowid

    cur.execute("""
    INSERT INTO flow_versions (flow_id, version, name, description, priority, trigger_type, trigger_value, nodes_json, edges_json, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        flow_id,
        1,
        "Main Welcome Flow",
        "Initial version",
        10,
        "contains",
        "hello,hi,مرحبا,السلام",
        json.dumps(welcome_nodes, ensure_ascii=False),
        json.dumps(welcome_edges, ensure_ascii=False),
        now
    ))

    # 2. Fallback Flow
    fallback_nodes = [
        {
            "id": "fb_1",
            "type": "start",
            "title": "Any Incoming Message",
            "position": {"x": 100, "y": 200},
            "data": {
                "trigger_type": "any",
                "trigger_value": ""
            }
        },
        {
            "id": "fb_2",
            "type": "send_text",
            "title": "Fallback Response",
            "position": {"x": 380, "y": 200},
            "data": {
                "message": "I did not understand your request.\n\nPlease type *hello* to see the main menu options."
            }
        },
        {
            "id": "fb_3",
            "type": "end",
            "title": "End",
            "position": {"x": 660, "y": 200},
            "data": {}
        }
    ]
    fallback_edges = [
        {"id": "fb_e1_2", "source": "fb_1", "target": "fb_2"},
        {"id": "fb_2_3", "source": "fb_2", "target": "fb_3"}
    ]

    cur.execute("""
    INSERT INTO flows (name, description, enabled, priority, is_default, trigger_type, trigger_value, nodes_json, edges_json, version, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        "Default Fallback Flow",
        "Executed when no other flow trigger matches the incoming message",
        1,
        1000,
        1,
        "any",
        "",
        json.dumps(fallback_nodes, ensure_ascii=False),
        json.dumps(fallback_edges, ensure_ascii=False),
        1,
        now,
        now
    ))
    fb_id = cur.lastrowid

    cur.execute("UPDATE bot_settings SET value = ? WHERE key = 'default_flow_id'", (str(fb_id),))

    conn.commit()
