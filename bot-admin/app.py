import os
import json
from functools import wraps
from flask import Flask, request, jsonify, render_template_string, session, redirect

app = Flask(__name__)

RULES_FILE = "/data/rules.json"

ADMIN_PASSWORD = os.environ.get("BOT_ADMIN_PASSWORD", "change-me")
app.secret_key = os.environ.get("BOT_ADMIN_SECRET", "change-this-secret")


def authenticated():
    return session.get("logged_in") is True


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not authenticated():
            return redirect("/login")
        return fn(*args, **kwargs)
    return wrapper


def load_rules():
    try:
        with open(RULES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {}

    return {
        "exact": data.get("exact", {}),
        "contains": data.get("contains", {})
    }


def save_rules(data):
    clean = {
        "exact": {},
        "contains": {}
    }

    for kind in ("exact", "contains"):
        rules = data.get(kind, {})

        if not isinstance(rules, dict):
            continue

        for trigger, reply in rules.items():
            trigger = str(trigger).strip()
            reply = str(reply).strip()

            if trigger and reply:
                clean[kind][trigger] = reply

    with open(RULES_FILE, "w", encoding="utf-8") as f:
        json.dump(
            clean,
            f,
            ensure_ascii=False,
            indent=2
        )


def find_reply(message, rules):
    text = (message or "").strip().lower()

    for trigger, reply in rules.get("exact", {}).items():
        if text == trigger.strip().lower():
            return {
                "matched": True,
                "type": "exact",
                "trigger": trigger,
                "reply": reply
            }

    for trigger, reply in rules.get("contains", {}).items():
        if trigger.strip().lower() in text:
            return {
                "matched": True,
                "type": "contains",
                "trigger": trigger,
                "reply": reply
            }

    return {
        "matched": False,
        "reply": None
    }


LOGIN_HTML = """
<!doctype html>
<html>
<head>
<meta charset="UTF-8">
<title>Bot Control Login</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body {
    font-family: Arial, sans-serif;
    background:#f4f6f8;
    margin:0;
    display:flex;
    justify-content:center;
    padding-top:80px;
}
.box {
    background:white;
    width:360px;
    max-width:90%;
    padding:28px;
    border-radius:10px;
    box-shadow:0 2px 12px rgba(0,0,0,.12);
}
h2 { margin-top:0; }
input {
    box-sizing:border-box;
    width:100%;
    padding:12px;
    font-size:16px;
    margin:10px 0;
}
button {
    width:100%;
    padding:12px;
    border:0;
    border-radius:6px;
    font-size:16px;
    cursor:pointer;
    background:#202c33;
    color:white;
}
.error { color:#b00020; }
</style>
</head>
<body>
<div class="box">
<h2>WhatsApp Bot Control</h2>
<form method="post">
<input type="password" name="password" placeholder="Admin password" required>
<button type="submit">Login</button>
{% if error %}
<p class="error">Incorrect password</p>
{% endif %}
</form>
</div>
</body>
</html>
"""


HTML = """
<!doctype html>
<html>
<head>
<meta charset="UTF-8">
<title>WhatsApp Bot Control</title>
<meta name="viewport" content="width=device-width,initial-scale=1">

<style>
body {
    font-family: Arial, sans-serif;
    margin:0;
    background:#f4f6f8;
    color:#222;
}

.header {
    background:#202c33;
    color:white;
    padding:18px 28px;
    display:flex;
    align-items:center;
    justify-content:space-between;
}

.header h2 {
    margin:0;
}

.header a {
    color:white;
}

.container {
    max-width:1200px;
    margin:24px auto;
    padding:0 18px;
}

.card {
    background:white;
    border-radius:9px;
    padding:20px;
    margin-bottom:20px;
    box-shadow:0 2px 8px rgba(0,0,0,.07);
}

h3 {
    margin-top:0;
}

.rule {
    display:grid;
    grid-template-columns:1fr 2fr auto;
    gap:10px;
    margin-bottom:10px;
}

input, textarea {
    box-sizing:border-box;
    width:100%;
    padding:10px;
    border:1px solid #ccc;
    border-radius:5px;
    font-size:15px;
}

button {
    padding:10px 16px;
    border:0;
    border-radius:5px;
    cursor:pointer;
    font-size:14px;
}

.primary {
    background:#202c33;
    color:white;
}

.add {
    background:#e8f1ed;
}

.delete {
    background:#f8e7e7;
}

.toolbar {
    display:flex;
    gap:10px;
    flex-wrap:wrap;
}

.status {
    padding:12px;
    margin-top:12px;
    border-radius:6px;
    display:none;
}

.success {
    display:block;
    background:#e8f5e9;
}

.error {
    display:block;
    background:#ffebee;
}

.test-result {
    margin-top:15px;
    background:#f5f5f5;
    padding:15px;
    border-radius:6px;
    white-space:pre-wrap;
}

@media(max-width:700px) {
    .rule {
        grid-template-columns:1fr;
    }
}
</style>
</head>

<body>

<div class="header">
    <h2>WhatsApp Bot Control</h2>
    <a href="/logout">Logout</a>
</div>

<div class="container">

<div class="card">

<h3>Exact Match</h3>

<p>
The customer's entire message must match the trigger.
</p>

<div id="exactRules"></div>

<button class="add" onclick="addRule('exact')">
+ Add Exact Rule
</button>

</div>


<div class="card">

<h3>Contains</h3>

<p>
The bot replies if the customer's message contains the trigger.
</p>

<div id="containsRules"></div>

<button class="add" onclick="addRule('contains')">
+ Add Contains Rule
</button>

</div>


<div class="card">

<h3>Test Bot Flow</h3>

<input
    id="testMessage"
    placeholder="Type a customer message, for example: hello"
>

<br><br>

<button class="primary" onclick="testMessage()">
Test Message
</button>

<div id="testResult" class="test-result">
Type a message above to test which rule would reply.
</div>

</div>


<div class="card">

<div class="toolbar">

<button class="primary" onclick="saveRules()">
Save Changes
</button>

<button onclick="loadRules()">
Reload
</button>

</div>

<div id="status" class="status"></div>

</div>

</div>


<script>

let rules = {
    exact: {},
    contains: {}
};


async function loadRules() {

    const response = await fetch('/api/rules');
    rules = await response.json();

    renderType('exact');
    renderType('contains');
}


function renderType(type) {

    const container =
        document.getElementById(type + 'Rules');

    container.innerHTML = '';

    Object.entries(rules[type]).forEach(
        ([trigger, reply]) => {

            const row = document.createElement('div');

            row.className = 'rule';

            const triggerInput =
                document.createElement('input');

            triggerInput.value = trigger;
            triggerInput.placeholder = 'Trigger';


            const replyInput =
                document.createElement('textarea');

            replyInput.value = reply;
            replyInput.placeholder = 'Bot reply';


            const deleteButton =
                document.createElement('button');

            deleteButton.className = 'delete';
            deleteButton.textContent = 'Delete';


            triggerInput.addEventListener(
                'input',
                collectRules
            );

            replyInput.addEventListener(
                'input',
                collectRules
            );

            deleteButton.addEventListener(
                'click',
                () => {
                    row.remove();
                    collectRules();
                }
            );


            row.dataset.type = type;

            row.appendChild(triggerInput);
            row.appendChild(replyInput);
            row.appendChild(deleteButton);

            container.appendChild(row);
        }
    );
}


function addRule(type) {

    collectRules();

    let name = 'new trigger';
    let n = 1;

    while (rules[type][name]) {
        name = 'new trigger ' + (++n);
    }

    rules[type][name] = 'New bot reply';

    renderType(type);
}


function collectRules() {

    const newRules = {
        exact: {},
        contains: {}
    };

    document
        .querySelectorAll('.rule')
        .forEach(row => {

            const type = row.dataset.type;

            const inputs =
                row.querySelectorAll(
                    'input, textarea'
                );

            const trigger =
                inputs[0].value.trim();

            const reply =
                inputs[1].value.trim();

            if (trigger && reply) {
                newRules[type][trigger] = reply;
            }

        });

    rules = newRules;
}


async function saveRules() {

    collectRules();

    const response = await fetch(
        '/api/rules',
        {
            method:'POST',
            headers:{
                'Content-Type':'application/json'
            },
            body:JSON.stringify(rules)
        }
    );

    const data = await response.json();

    const status =
        document.getElementById('status');

    if (response.ok) {
        status.className =
            'status success';

        status.textContent =
            'Saved. New rules are active immediately.';
    } else {
        status.className =
            'status error';

        status.textContent =
            data.error || 'Save failed';
    }
}


async function testMessage() {

    collectRules();

    const message =
        document.getElementById(
            'testMessage'
        ).value;

    const response = await fetch(
        '/api/test',
        {
            method:'POST',
            headers:{
                'Content-Type':'application/json'
            },
            body:JSON.stringify({
                message:message,
                rules:rules
            })
        }
    );

    const result =
        await response.json();

    const box =
        document.getElementById(
            'testResult'
        );

    if (result.matched) {

        box.textContent =
            'MATCHED: ' +
            result.type +
            '\\nTrigger: ' +
            result.trigger +
            '\\n\\nBot reply:\\n' +
            result.reply;

    } else {

        box.textContent =
            'No rule matched this message.';
    }
}


loadRules();

</script>

</body>
</html>
"""


@app.route("/login", methods=["GET", "POST"])
def login():

    error = False

    if request.method == "POST":

        if request.form.get("password") == ADMIN_PASSWORD:

            session["logged_in"] = True

            return redirect("/")

        error = True

    return render_template_string(
        LOGIN_HTML,
        error=error
    )


@app.route("/logout")
def logout():

    session.clear()

    return redirect("/login")


@app.route("/")
@login_required
def index():

    return render_template_string(HTML)


@app.route("/api/rules")
@login_required
def get_rules():

    return jsonify(load_rules())


@app.route("/api/rules", methods=["POST"])
@login_required
def update_rules():

    try:

        data = request.get_json(force=True)

        save_rules(data)

        return jsonify({
            "saved": True
        })

    except Exception as e:

        return jsonify({
            "error": str(e)
        }), 500


@app.route("/api/test", methods=["POST"])
@login_required
def test():

    data = request.get_json(force=True)

    message = data.get("message", "")

    rules = data.get("rules")

    if not rules:
        rules = load_rules()

    return jsonify(
        find_reply(message, rules)
    )


@app.route("/health")
def health():

    return jsonify({
        "status": "ok"
    })


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=2003
    )
