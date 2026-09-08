import os
import requests
from flask import Flask, jsonify, render_template_string

app = Flask(__name__)

WAHA_URL = os.environ.get("WAHA_URL", "http://waha:3000")
WAHA_API_KEY = os.environ.get("WAHA_API_KEY", "")
WAHA_SESSION = os.environ.get("WAHA_SESSION", "test")

HEADERS = {}
if WAHA_API_KEY:
    HEADERS["X-Api-Key"] = WAHA_API_KEY


def clean_number(value):
    if not value:
        return ""

    value = str(value)

    for suffix in [
        "@s.whatsapp.net",
        "@c.us",
        "@lid"
    ]:
        if value.endswith(suffix):
            value = value[:-len(suffix)]

    return value


def get_all_contacts():
    contacts = []
    limit = 500
    offset = 0

    while True:
        r = requests.get(
            f"{WAHA_URL}/api/contacts/all",
            headers=HEADERS,
            params={
                "session": WAHA_SESSION,
                "limit": limit,
                "offset": offset
            },
            timeout=60
        )

        r.raise_for_status()
        batch = r.json()

        if not isinstance(batch, list):
            break

        contacts.extend(batch)

        if len(batch) < limit:
            break

        offset += limit

    return contacts


def get_lid_map():
    mappings = {}
    limit = 500
    offset = 0

    while True:
        r = requests.get(
            f"{WAHA_URL}/api/{WAHA_SESSION}/lids",
            headers=HEADERS,
            params={
                "limit": limit,
                "offset": offset
            },
            timeout=60
        )

        if not r.ok:
            return mappings

        batch = r.json()

        if not isinstance(batch, list):
            break

        for item in batch:
            lid = item.get("lid")
            pn = item.get("pn")

            if lid and pn:
                mappings[lid] = clean_number(pn)

        if len(batch) < limit:
            break

        offset += limit

    return mappings


@app.route("/api/contacts")
def contacts_api():
    try:
        contacts = get_all_contacts()
        lid_map = get_lid_map()

        result = []
        seen = set()

        for c in contacts:
            contact_id = c.get("id", "")

            # Ignore WhatsApp groups
            if contact_id.endswith("@g.us"):
                continue

            # Ignore broadcasts/status
            if contact_id.endswith("@broadcast"):
                continue

            if contact_id == "status@broadcast":
                continue

            name = (
                c.get("name")
                or c.get("pushname")
                or c.get("shortName")
                or ""
            )

            phone = clean_number(
                c.get("phoneNumber")
                or c.get("number")
            )

            lid = c.get("lid")

            # If no direct phone number, try LID mapping
            if not phone and lid:
                phone = lid_map.get(lid, "")

            if not phone and contact_id.endswith("@lid"):
                phone = lid_map.get(contact_id, "")

            # If ID itself is a phone-number based WhatsApp ID
            if not phone and (
                contact_id.endswith("@c.us")
                or contact_id.endswith("@s.whatsapp.net")
            ):
                phone = clean_number(contact_id)

            # We only want actual contacts that have a known number
            if not phone:
                continue

            # Avoid duplicates
            if phone in seen:
                continue

            seen.add(phone)

            result.append({
                "name": name or "Unknown",
                "number": phone,
                "id": contact_id
            })

        result.sort(
            key=lambda x: (
                x["name"].lower(),
                x["number"]
            )
        )

        return jsonify(result)

    except Exception as e:
        return jsonify({
            "error": str(e)
        }), 500


HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">

    <title>WhatsApp Contacts</title>

    <meta
        name="viewport"
        content="width=device-width, initial-scale=1"
    >

    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 0;
            background: #f4f6f8;
            color: #222;
        }

        .header {
            background: #202c33;
            color: white;
            padding: 20px 30px;
        }

        .header h1 {
            margin: 0;
        }

        .container {
            max-width: 1300px;
            margin: 25px auto;
            padding: 0 20px;
        }

        .toolbar {
            display: flex;
            gap: 10px;
            margin-bottom: 15px;
        }

        input {
            flex: 1;
            padding: 12px;
            font-size: 16px;
            border: 1px solid #ccc;
            border-radius: 6px;
        }

        button {
            padding: 12px 20px;
            border: 0;
            border-radius: 6px;
            cursor: pointer;
            font-size: 15px;
        }

        .count {
            margin-bottom: 12px;
            font-weight: bold;
        }

        .card {
            background: white;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 2px 8px rgba(0,0,0,.08);
        }

        table {
            width: 100%;
            border-collapse: collapse;
        }

        th {
            background: #eee;
            text-align: left;
            padding: 12px;
            position: sticky;
            top: 0;
        }

        td {
            padding: 12px;
            border-top: 1px solid #eee;
        }

        tr:hover {
            background: #fafafa;
        }

        .phone {
            font-family: monospace;
            font-size: 15px;
        }

        .id {
            color: #777;
            font-size: 13px;
        }

        #loading {
            padding: 30px;
            text-align: center;
        }
    </style>
</head>

<body>

<div class="header">
    <h1>WhatsApp Contacts</h1>
</div>

<div class="container">

    <div class="toolbar">

        <input
            id="search"
            placeholder="Search name or phone number..."
            oninput="renderContacts()"
        >

        <button onclick="loadContacts()">
            Refresh
        </button>

    </div>

    <div
        class="count"
        id="count">
    </div>

    <div class="card">

        <div id="loading">
            Loading WhatsApp contacts...
        </div>

        <table
            id="contactsTable"
            style="display:none;"
        >

            <thead>
                <tr>
                    <th>Name</th>
                    <th>Phone Number</th>
                    <th>WhatsApp ID</th>
                </tr>
            </thead>

            <tbody id="contactsBody"></tbody>

        </table>

    </div>

</div>

<script>

let contacts = [];


async function loadContacts() {

    document.getElementById("loading").style.display =
        "block";

    document.getElementById("loading").innerText =
        "Loading WhatsApp contacts...";

    document.getElementById("contactsTable").style.display =
        "none";

    try {

        const response =
            await fetch("/api/contacts");

        const data =
            await response.json();

        if (!response.ok) {
            throw new Error(
                data.error || "Unable to load contacts"
            );
        }

        contacts = data;

        renderContacts();

        document.getElementById("loading").style.display =
            "none";

        document.getElementById("contactsTable").style.display =
            "table";

    } catch (error) {

        document.getElementById("loading").innerText =
            "Error: " + error.message;

    }

}


function escapeHtml(value) {

    const div =
        document.createElement("div");

    div.textContent =
        value || "";

    return div.innerHTML;
}


function renderContacts() {

    const search =
        document
        .getElementById("search")
        .value
        .toLowerCase();

    const filtered =
        contacts.filter(c => {

            return (
                (c.name || "")
                    .toLowerCase()
                    .includes(search)
                ||
                (c.number || "")
                    .toLowerCase()
                    .includes(search)
                ||
                (c.id || "")
                    .toLowerCase()
                    .includes(search)
            );

        });


    const body =
        document.getElementById("contactsBody");

    body.innerHTML = "";


    filtered.forEach(c => {

        const row =
            document.createElement("tr");

        row.innerHTML = `
            <td>
                ${escapeHtml(c.name)}
            </td>

            <td class="phone">
                ${escapeHtml(c.number)}
            </td>

            <td class="id">
                ${escapeHtml(c.id)}
            </td>
        `;

        body.appendChild(row);

    });


    document.getElementById("count").innerText =
        filtered.length +
        " contacts with phone numbers";

}


loadContacts();

</script>

</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(HTML)


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=2001
    )
