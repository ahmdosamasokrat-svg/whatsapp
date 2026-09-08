// ============================================================
// WhatsApp Bot Flow Builder - Main Frontend Application
// ============================================================

const API_BASE = "";

// Application State
const state = {
  currentPage: "dashboard",
  botEnabled: true,
  defaultSession: "test",
  flows: [],
  currentFlow: null,
  selectedNodeId: null,
  canvas: {
    scale: 1,
    panX: 40,
    panY: 40,
    isPanning: false,
    startX: 0,
    startY: 0
  },
  draggingNode: null,
  dragOffset: { x: 0, y: 0 },
  connecting: null, // { nodeId, handle, isOutput, startX, startY }
  autosaveTimer: null,
  hasUnsavedChanges: false,
  simSession: {
    status: "idle",
    waitingNodeId: null,
    variables: {},
    trace: []
  },
  activeConversationId: null
};

// Node Type Definitions & Badges
const NODE_META = {
  start: { title: "Incoming Message", icon: "fa-bolt", bg: "bg-green", color: "#10b981" },
  send_text: { title: "Send Text", icon: "fa-comment-dots", bg: "bg-blue", color: "#3b82f6" },
  condition: { title: "Condition", icon: "fa-code-branch", bg: "bg-yellow", color: "#f59e0b" },
  menu: { title: "Menu / Choice", icon: "fa-list-ol", bg: "bg-purple", color: "#8b5cf6" },
  wait_for_reply: { title: "Wait For Reply", icon: "fa-hourglass-half", bg: "bg-orange", color: "#f97316" },
  set_variable: { title: "Set Variable", icon: "fa-square-root-variable", bg: "bg-indigo", color: "#6366f1" },
  send_image: { title: "Send Image", icon: "fa-image", bg: "bg-teal", color: "#14b8a6" },
  send_file: { title: "Send File", icon: "fa-file-pdf", bg: "bg-cyan", color: "#06b6d4" },
  delay: { title: "Delay", icon: "fa-clock", bg: "bg-gray", color: "#64748b" },
  http_request: { title: "HTTP Request", icon: "fa-network-wired", bg: "bg-red", color: "#ef4444" },
  human_handoff: { title: "Human Handoff", icon: "fa-headset", bg: "bg-pink", color: "#ec4899" },
  end: { title: "End Flow", icon: "fa-flag-checkered", bg: "bg-dark", color: "#1e293b" }
};

// Initialize App
document.addEventListener("DOMContentLoaded", () => {
  setupNavigation();
  setupGlobalBotSwitch();
  setupCanvasEvents();
  setupConversationPolling();
  loadDashboard();
});

// Toast Notifications
function showToast(msg, isError = false) {
  const toast = document.getElementById("toast");
  toast.innerHTML = (isError ? '<i class="fa-solid fa-triangle-exclamation text-danger"></i> ' : '<i class="fa-solid fa-circle-check text-green"></i> ') + msg;
  toast.className = "toast show";
  setTimeout(() => {
    toast.className = "toast";
  }, 3500);
}

// Navigation Handling
function setupNavigation() {
  document.querySelectorAll(".nav-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const page = btn.getAttribute("data-page");
      switchPage(page);
    });
  });
}

function switchPage(pageId) {
  state.currentPage = pageId;
  document.querySelectorAll(".nav-btn").forEach(btn => {
    btn.classList.toggle("active", btn.getAttribute("data-page") === pageId);
  });
  document.querySelectorAll(".page").forEach(page => {
    page.classList.toggle("active", page.id === `page-${pageId}`);
  });

  if (pageId === "dashboard") loadDashboard();
  if (pageId === "flows") loadFlows();
  if (pageId === "contacts") loadContacts();
  if (pageId === "conversations") loadConversations();
  if (pageId === "logs") loadLogs();
  if (pageId === "settings") loadSettings();
}

// Global Bot Toggle
function setupGlobalBotSwitch() {
  const sw = document.getElementById("globalBotSwitch");
  sw.addEventListener("change", async () => {
    const enabled = sw.checked;
    try {
      const resp = await fetch(`${API_BASE}/api/settings`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ bot_enabled: enabled ? "true" : "false" })
      });
      if (resp.ok) {
        state.botEnabled = enabled;
        updateBotStatusBadge(enabled);
        showToast(`Global Bot turned ${enabled ? "ON" : "OFF"}`);
      }
    } catch (e) {
      showToast("Failed to update bot state", true);
    }
  });
}

function updateBotStatusBadge(enabled) {
  const tag = document.getElementById("botStatusTag");
  const sw = document.getElementById("globalBotSwitch");
  sw.checked = enabled;
  tag.textContent = enabled ? "ON" : "OFF";
  tag.className = `status-tag ${enabled ? "" : "off"}`;
  const statBot = document.getElementById("statBotStatus");
  if (statBot) {
    statBot.textContent = enabled ? "Active" : "Disabled";
    statBot.className = enabled ? "text-green" : "text-muted";
  }
}

// -------------------------------------------------------------
// DASHBOARD
// -------------------------------------------------------------
async function loadDashboard() {
  try {
    const resp = await fetch(`${API_BASE}/api/dashboard`);
    if (!resp.ok) return;
    const data = await resp.json();

    state.botEnabled = data.bot_enabled;
    updateBotStatusBadge(data.bot_enabled);

    // Update Header Session Badge
    const sessText = document.getElementById("sessionStatusText");
    sessText.textContent = `WAHA: ${data.session_status || "UNKNOWN"}`;

    // Update Stats Cards
    document.getElementById("statSessionName").textContent = `Session: ${data.session_name}`;
    document.getElementById("statFlows").textContent = `${data.flows.active} / ${data.flows.total}`;
    document.getElementById("statConversations").textContent = data.conversations.total;
    document.getElementById("statConvSub").textContent = `${data.conversations.waiting_reply} waiting • ${data.conversations.human_mode} human`;
    document.getElementById("statContacts").textContent = data.contacts.total;
    document.getElementById("statBotDisabledContacts").textContent = `${data.contacts.bot_disabled} paused for human`;
    document.getElementById("statMessages").textContent = data.messages.total;
    document.getElementById("statMsgBreakdown").textContent = `↓ ${data.messages.incoming} incoming • ↑ ${data.messages.outgoing} outgoing`;

    // Render Recent Flows
    const flowsResp = await fetch(`${API_BASE}/api/flows`);
    if (flowsResp.ok) {
      const flows = await flowsResp.json();
      state.flows = flows;
      renderDashboardFlows(flows.slice(0, 5));
    }

    // Render Recent Logs
    renderDashboardLogs(data.recent_logs || []);
  } catch (e) {
    console.error("Dashboard error:", e);
  }
}

function renderDashboardFlows(flows) {
  const container = document.getElementById("dashFlowsList");
  if (!flows.length) {
    container.innerHTML = `<div class="text-center text-muted p-4">No flows created yet. Click "+ New Flow" to create one.</div>`;
    return;
  }
  container.innerHTML = flows.map(f => `
    <div class="dash-item">
      <div class="dash-item-info">
        <span class="dash-item-title">${escapeHtml(f.name)} ${f.is_default ? '<span class="badge badge-yellow">Fallback</span>' : ''}</span>
        <span class="dash-item-sub">Trigger: <strong>${escapeHtml(f.trigger_type)}</strong> ${f.trigger_value ? `(${escapeHtml(f.trigger_value)})` : ''} • Priority: ${f.priority}</span>
      </div>
      <div class="d-flex align-center gap-2">
        <span class="badge ${f.enabled ? 'badge-green' : 'badge-gray'}">${f.enabled ? 'Enabled' : 'Disabled'}</span>
        <button class="btn btn-sm btn-outline" onclick="openFlowEditor(${f.id})"><i class="fa-solid fa-pen"></i> Edit</button>
      </div>
    </div>
  `).join("");
}

function renderDashboardLogs(logs) {
  const container = document.getElementById("dashLogsList");
  if (!logs.length) {
    container.innerHTML = `<div class="text-center text-muted p-4">No activity logged yet.</div>`;
    return;
  }
  container.innerHTML = logs.map(l => {
    let iconClass = "fa-info text-blue";
    if (l.direction === "incoming") iconClass = "fa-arrow-down text-green";
    if (l.direction === "outgoing") iconClass = "fa-arrow-up text-blue";
    if (l.direction === "error") iconClass = "fa-circle-xmark text-danger";
    return `
      <div class="dash-item">
        <div class="d-flex align-center gap-2">
          <i class="fa-solid ${iconClass}"></i>
          <div class="dash-item-info">
            <span class="dash-item-title">${escapeHtml(l.event_type)} ${l.contact_id ? `(${escapeHtml(l.contact_id)})` : ''}</span>
            <span class="dash-item-sub">${escapeHtml(l.message_text || "")}</span>
          </div>
        </div>
        <span class="text-muted" style="font-size: 11px;">${l.timestamp.split(" ")[1] || l.timestamp}</span>
      </div>
    `;
  }).join("");
}

// -------------------------------------------------------------
// FLOWS LIST PAGE
// -------------------------------------------------------------
async function loadFlows() {
  const tbody = document.getElementById("flowsTableBody");
  tbody.innerHTML = `<tr><td colspan="7" class="text-center p-4"><i class="fa-solid fa-spinner fa-spin"></i> Loading flows...</td></tr>`;

  try {
    const resp = await fetch(`${API_BASE}/api/flows`);
    if (!resp.ok) return;
    const flows = await resp.json();
    state.flows = flows;

    if (!flows.length) {
      tbody.innerHTML = `<tr><td colspan="7" class="text-center p-4">No flows found. Click "+ New Flow" to build your first flow.</td></tr>`;
      return;
    }

    tbody.innerHTML = flows.map(f => `
      <tr>
        <td>
          <label class="switch switch-sm">
            <input type="checkbox" ${f.enabled ? "checked" : ""} onchange="toggleFlowEnabled(${f.id})">
            <span class="slider round"></span>
          </label>
        </td>
        <td>
          <strong>${escapeHtml(f.name)}</strong>
          ${f.is_default ? '<span class="badge badge-yellow ml-1">Fallback</span>' : ''}
          <br><small class="text-muted">${escapeHtml(f.description || "No description")}</small>
        </td>
        <td>
          <span class="badge badge-blue">${escapeHtml(f.trigger_type)}</span>
          <span class="text-muted" style="font-size: 12px;">${escapeHtml(f.trigger_value || "*")}</span>
        </td>
        <td><span class="badge badge-purple">${f.priority}</span></td>
        <td>${f.node_count} nodes</td>
        <td><small class="text-muted">${f.updated_at}</small></td>
        <td class="text-right">
          <div class="d-flex justify-content-end gap-1">
            <button class="btn btn-sm btn-primary" onclick="openFlowEditor(${f.id})" title="Visual Flow Editor"><i class="fa-solid fa-pen-to-square"></i> Edit</button>
            <button class="btn btn-sm btn-outline" onclick="duplicateFlow(${f.id})" title="Duplicate Flow"><i class="fa-solid fa-copy"></i></button>
            <button class="btn btn-sm btn-outline" onclick="exportFlow(${f.id})" title="Export JSON"><i class="fa-solid fa-download"></i></button>
            <button class="btn btn-sm btn-outline text-danger" onclick="deleteFlow(${f.id})" title="Delete Flow"><i class="fa-solid fa-trash"></i></button>
          </div>
        </td>
      </tr>
    `).join("");
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="7" class="text-center text-danger p-4">Error loading flows.</td></tr>`;
  }
}

async function toggleFlowEnabled(flowId) {
  try {
    const resp = await fetch(`${API_BASE}/api/flows/${flowId}/toggle`, { method: "POST" });
    if (resp.ok) {
      showToast("Flow status updated");
    }
  } catch (e) {
    showToast("Failed to toggle flow", true);
  }
}

async function duplicateFlow(flowId) {
  try {
    const resp = await fetch(`${API_BASE}/api/flows/${flowId}/duplicate`, { method: "POST" });
    if (resp.ok) {
      showToast("Flow duplicated successfully");
      loadFlows();
    }
  } catch (e) {
    showToast("Failed to duplicate flow", true);
  }
}

async function deleteFlow(flowId) {
  if (!confirm("Are you sure you want to delete this flow? This cannot be undone.")) return;
  try {
    const resp = await fetch(`${API_BASE}/api/flows/${flowId}`, { method: "DELETE" });
    if (resp.ok) {
      showToast("Flow deleted");
      loadFlows();
    }
  } catch (e) {
    showToast("Failed to delete flow", true);
  }
}

function openNewFlowModal() {
  document.getElementById("newFlowName").value = "";
  document.getElementById("newFlowDesc").value = "";
  document.getElementById("newFlowTriggerVal").value = "";
  document.getElementById("newFlowPriority").value = "10";
  document.getElementById("newFlowIsDefault").checked = false;
  openModal("newFlowModal");
}

async function submitCreateFlow() {
  const name = document.getElementById("newFlowName").value.trim();
  if (!name) {
    alert("Please enter a flow name.");
    return;
  }
  const desc = document.getElementById("newFlowDesc").value.trim();
  const ttype = document.getElementById("newFlowTriggerType").value;
  const tval = document.getElementById("newFlowTriggerVal").value.trim();
  const priority = parseInt(document.getElementById("newFlowPriority").value) || 100;
  const isDefault = document.getElementById("newFlowIsDefault").checked ? 1 : 0;

  try {
    const resp = await fetch(`${API_BASE}/api/flows`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name,
        description: desc,
        trigger_type: ttype,
        trigger_value: tval,
        priority,
        is_default: isDefault
      })
    });
    if (resp.ok) {
      const data = await resp.json();
      closeModal("newFlowModal");
      showToast("Flow created! Opening visual editor...");
      openFlowEditor(data.id);
    }
  } catch (e) {
    showToast("Failed to create flow", true);
  }
}

function openImportFlowModal() {
  document.getElementById("importJsonText").value = "";
  document.getElementById("importFileInput").value = "";
  openModal("importFlowModal");
}

function handleImportFile(event) {
  const file = event.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = (e) => {
    document.getElementById("importJsonText").value = e.target.result;
  };
  reader.readAsText(file);
}

async function submitImportFlow() {
  const raw = document.getElementById("importJsonText").value.trim();
  if (!raw) {
    alert("Please paste JSON or upload a file.");
    return;
  }
  try {
    const data = JSON.parse(raw);
    const resp = await fetch(`${API_BASE}/api/flows/import`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data)
    });
    if (resp.ok) {
      closeModal("importFlowModal");
      showToast("Flow imported successfully!");
      loadFlows();
    } else {
      showToast("Import error", true);
    }
  } catch (e) {
    alert("Invalid JSON format.");
  }
}

// -------------------------------------------------------------
// VISUAL FLOW BUILDER & CANVAS
// -------------------------------------------------------------
async function openFlowEditor(flowId) {
  switchPage("builder");
  try {
    const resp = await fetch(`${API_BASE}/api/flows/${flowId}`);
    if (!resp.ok) return;
    const flow = await resp.json();
    state.currentFlow = flow;

    // Set toolbar fields
    document.getElementById("builderFlowName").value = flow.name;
    document.getElementById("builderFlowVersion").textContent = `v${flow.version || 1}`;
    document.getElementById("builderFlowPriority").value = flow.priority || 10;
    document.getElementById("builderFlowIsDefault").checked = !!flow.is_default;
    document.getElementById("builderFlowEnabled").checked = !!flow.enabled;

    setSaveStatus("Saved");

    // Reset view position
    state.canvas.scale = 1;
    state.canvas.panX = 40;
    state.canvas.panY = 40;
    updateCanvasTransform();

    // Render Canvas
    renderCanvas();
    deselectNode();
  } catch (e) {
    showToast("Error loading flow", true);
  }
}

function renderCanvas() {
  const nodesLayer = document.getElementById("nodesLayer");
  const edgesGroup = document.getElementById("edgesGroup");
  nodesLayer.innerHTML = "";
  edgesGroup.innerHTML = "";

  if (!state.currentFlow) return;

  const nodes = state.currentFlow.nodes || [];
  const edges = state.currentFlow.edges || [];

  // Render Nodes
  nodes.forEach(node => {
    const nodeEl = createNodeElement(node);
    nodesLayer.appendChild(nodeEl);
  });

  // Render Edges
  edges.forEach(edge => {
    const edgePath = createEdgeElement(edge);
    if (edgePath) edgesGroup.appendChild(edgePath);
  });
}

function createNodeElement(node) {
  const meta = NODE_META[node.type] || { title: node.type, icon: "fa-cube", bg: "bg-blue", color: "#3b82f6" };
  const el = document.createElement("div");
  el.className = `flow-node ${state.selectedNodeId === node.id ? "selected" : ""}`;
  el.id = `node-${node.id}`;
  el.style.left = `${node.position.x}px`;
  el.style.top = `${node.position.y}px`;

  // Dynamic preview snippet
  let summary = "";
  const d = node.data || {};
  if (node.type === "start") {
    summary = `Trigger: ${d.trigger_type || "contains"} ${d.trigger_value ? `(${d.trigger_value})` : ""}`;
  } else if (node.type === "send_text") {
    summary = d.message || "Empty message";
  } else if (node.type === "condition") {
    summary = `If ${d.field || "message.text"} ${d.operator || "equals"} "${d.value || ""}"`;
  } else if (node.type === "menu") {
    const optCount = (d.options || []).length;
    summary = `${optCount} options: ${(d.options || []).map(o => o.value || o.id).join(", ")}`;
  } else if (node.type === "wait_for_reply") {
    summary = d.variable_name ? `Store in: {{${d.variable_name}}}` : "Wait for response";
  } else if (node.type === "set_variable") {
    summary = `${d.variable_name || "var"} = ${d.variable_value || '""'}`;
  } else if (node.type === "send_image") {
    summary = d.image_url ? `URL: ${d.image_url}` : "No image set";
  } else if (node.type === "send_file") {
    summary = d.file_url ? `File: ${d.filename || d.file_url}` : "No file set";
  } else if (node.type === "delay") {
    summary = `Wait ${d.seconds || 2} seconds`;
  } else if (node.type === "http_request") {
    summary = `${d.method || "POST"} ${d.url || "https://..."}`;
  } else if (node.type === "human_handoff") {
    summary = "Transfer chat to human agent";
  } else if (node.type === "end") {
    summary = "Complete flow";
  }

  // Branch handles for condition and menu nodes
  let branchesHtml = "";
  if (node.type === "condition") {
    branchesHtml = `
      <div class="node-branches">
        <div class="node-branch-row">
          <span class="text-green font-weight-bold">YES</span>
          <div class="node-branch-port" data-node-id="${node.id}" data-handle="yes" title="Connect YES path"></div>
        </div>
        <div class="node-branch-row">
          <span class="text-danger font-weight-bold">NO</span>
          <div class="node-branch-port" data-node-id="${node.id}" data-handle="no" title="Connect NO path"></div>
        </div>
      </div>
    `;
  } else if (node.type === "menu") {
    const opts = d.options || [];
    branchesHtml = `
      <div class="node-branches">
        ${opts.map(o => `
          <div class="node-branch-row">
            <span>${escapeHtml(o.label || o.value || o.id)}</span>
            <div class="node-branch-port" data-node-id="${node.id}" data-handle="${o.id}" title="Route for ${escapeHtml(o.label || o.value)}"></div>
          </div>
        `).join("")}
        <div class="node-branch-row text-muted">
          <span>otherwise</span>
          <div class="node-branch-port" data-node-id="${node.id}" data-handle="otherwise" title="Fallback route"></div>
        </div>
      </div>
    `;
  }

  el.innerHTML = `
    <!-- Input Port (not for Start node) -->
    ${node.type !== "start" ? `<div class="node-port node-port-in" data-node-id="${node.id}" data-port="in" title="Incoming connection"></div>` : ""}

    <div class="node-header ${meta.bg}">
      <div class="node-header-title">
        <i class="fa-solid ${meta.icon}"></i>
        <span>${escapeHtml(node.title || meta.title)}</span>
      </div>
    </div>
    <div class="node-body">
      <div class="node-summary">${escapeHtml(summary)}</div>
    </div>

    <!-- Default Output Port (for linear nodes) -->
    ${!["condition", "menu", "end", "human_handoff"].includes(node.type) ? `
      <div class="node-port node-port-out" data-node-id="${node.id}" data-port="out" title="Connect to next step"></div>
    ` : ""}

    ${branchesHtml}
  `;

  // Select Node
  el.addEventListener("mousedown", (e) => {
    if (e.target.classList.contains("node-port") || e.target.classList.contains("node-branch-port")) return;
    selectNode(node.id);
    startNodeDrag(node.id, e);
  });

  return el;
}

// Edge Element (SVG Path)
function createEdgeElement(edge) {
  const sourceNode = (state.currentFlow.nodes || []).find(n => n.id === edge.source);
  const targetNode = (state.currentFlow.nodes || []).find(n => n.id === edge.target);
  if (!sourceNode || !targetNode) return null;

  const startPt = getNodePortPosition(edge.source, edge.sourceHandle, true);
  const endPt = getNodePortPosition(edge.target, null, false);

  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  const d = calculateBezierPath(startPt.x, startPt.y, endPt.x, endPt.y);
  path.setAttribute("d", d);
  path.setAttribute("class", "edge-path");
  path.setAttribute("id", `edge-${edge.id}`);
  path.setAttribute("marker-end", "url(#arrow)");

  // Click to delete edge
  path.addEventListener("click", (e) => {
    e.stopPropagation();
    if (confirm("Delete this connection wire?")) {
      deleteEdge(edge.id);
    }
  });

  return path;
}

function getNodePortPosition(nodeId, handle, isOutput) {
  const node = (state.currentFlow.nodes || []).find(n => n.id === nodeId);
  if (!node) return { x: 0, y: 0 };

  const x = node.position.x;
  const y = node.position.y;
  const width = 220;

  if (!isOutput) {
    return { x: x, y: y + 36 };
  }

  // If handle specified on menu/condition
  if (handle) {
    const el = document.getElementById(`node-${nodeId}`);
    if (el) {
      const portEl = el.querySelector(`[data-handle="${handle}"]`);
      if (portEl) {
        return {
          x: x + width,
          y: y + portEl.offsetTop + 5
        };
      }
    }
  }

  return { x: x + width, y: y + 36 };
}

function calculateBezierPath(x1, y1, x2, y2) {
  const dx = Math.max(Math.abs(x2 - x1) * 0.5, 40);
  return `M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`;
}

// -------------------------------------------------------------
// CANVAS INTERACTIVITY (PAN, ZOOM, DRAG, CONNECT)
// -------------------------------------------------------------
function setupCanvasEvents() {
  const wrapper = document.getElementById("canvasWrapper");

  // Pan canvas
  wrapper.addEventListener("mousedown", (e) => {
    if (e.target === wrapper || e.target.id === "canvasSvg" || e.target.id === "nodesLayer") {
      deselectNode();
      state.canvas.isPanning = true;
      state.canvas.startX = e.clientX - state.canvas.panX;
      state.canvas.startY = e.clientY - state.canvas.panY;
      wrapper.classList.add("panning");
    }
  });

  window.addEventListener("mousemove", (e) => {
    // Panning
    if (state.canvas.isPanning) {
      state.canvas.panX = e.clientX - state.canvas.startX;
      state.canvas.panY = e.clientY - state.canvas.startY;
      updateCanvasTransform();
    }

    // Node Dragging
    if (state.draggingNode) {
      const node = (state.currentFlow.nodes || []).find(n => n.id === state.draggingNode);
      if (node) {
        const mouseX = (e.clientX - state.canvas.panX) / state.canvas.scale;
        const mouseY = (e.clientY - state.canvas.panY) / state.canvas.scale;
        node.position.x = Math.round((mouseX - state.dragOffset.x) / 10) * 10;
        node.position.y = Math.round((mouseY - state.dragOffset.y) / 10) * 10;

        const el = document.getElementById(`node-${node.id}`);
        if (el) {
          el.style.left = `${node.position.x}px`;
          el.style.top = `${node.position.y}px`;
        }
        updateConnectedEdges(node.id);
        markUnsaved();
      }
    }

    // Wire Drawing
    if (state.connecting) {
      const mouseX = (e.clientX - state.canvas.panX) / state.canvas.scale;
      const mouseY = (e.clientY - state.canvas.panY) / state.canvas.scale;
      const tempPath = document.getElementById("tempConnectionPath");
      tempPath.style.display = "block";
      tempPath.setAttribute("d", calculateBezierPath(state.connecting.startX, state.connecting.startY, mouseX, mouseY));
    }
  });

  window.addEventListener("mouseup", (e) => {
    if (state.canvas.isPanning) {
      state.canvas.isPanning = false;
      wrapper.classList.remove("panning");
    }
    if (state.draggingNode) {
      state.draggingNode = null;
    }
    if (state.connecting) {
      // Check if dropped on an input port
      const target = document.elementFromPoint(e.clientX, e.clientY);
      if (target && target.classList.contains("node-port-in")) {
        const targetNodeId = target.getAttribute("data-node-id");
        if (targetNodeId && targetNodeId !== state.connecting.nodeId) {
          addEdge(state.connecting.nodeId, targetNodeId, state.connecting.handle);
        }
      }
      state.connecting = null;
      document.getElementById("tempConnectionPath").style.display = "none";
    }
  });

  // Zoom canvas with wheel
  wrapper.addEventListener("wheel", (e) => {
    e.preventDefault();
    const zoomFactor = e.deltaY < 0 ? 1.08 : 0.92;
    setCanvasZoom(state.canvas.scale * zoomFactor);
  });

  // Connect port mousedown delegation
  wrapper.addEventListener("mousedown", (e) => {
    const port = e.target.closest(".node-port-out, .node-branch-port");
    if (!port) return;
    e.stopPropagation();

    const nodeId = port.getAttribute("data-node-id");
    const handle = port.getAttribute("data-handle") || null;
    const pt = getNodePortPosition(nodeId, handle, true);

    state.connecting = {
      nodeId,
      handle,
      startX: pt.x,
      startY: pt.y
    };
  });
}

function updateCanvasTransform() {
  const container = document.getElementById("canvasContainer");
  container.style.transform = `translate(${state.canvas.panX}px, ${state.canvas.panY}px) scale(${state.canvas.scale})`;
}

function setCanvasZoom(newScale) {
  state.canvas.scale = Math.min(Math.max(newScale, 0.3), 2.5);
  updateCanvasTransform();
}

function canvasZoomIn() { setCanvasZoom(state.canvas.scale * 1.2); }
function canvasZoomOut() { setCanvasZoom(state.canvas.scale * 0.8); }
function canvasResetZoom() {
  state.canvas.scale = 1;
  state.canvas.panX = 40;
  state.canvas.panY = 40;
  updateCanvasTransform();
}

function canvasAutoLayout() {
  if (!state.currentFlow) return;
  const nodes = state.currentFlow.nodes || [];
  nodes.forEach((n, idx) => {
    n.position.x = 100 + (idx % 4) * 280;
    n.position.y = 120 + Math.floor(idx / 4) * 200;
  });
  renderCanvas();
  markUnsaved();
}

function startNodeDrag(nodeId, e) {
  state.draggingNode = nodeId;
  const node = (state.currentFlow.nodes || []).find(n => n.id === nodeId);
  if (!node) return;
  const mouseX = (e.clientX - state.canvas.panX) / state.canvas.scale;
  const mouseY = (e.clientY - state.canvas.panY) / state.canvas.scale;
  state.dragOffset.x = mouseX - node.position.x;
  state.dragOffset.y = mouseY - node.position.y;
}

function updateConnectedEdges(nodeId) {
  if (!state.currentFlow) return;
  (state.currentFlow.edges || []).forEach(edge => {
    if (edge.source === nodeId || edge.target === nodeId) {
      const path = document.getElementById(`edge-${edge.id}`);
      if (path) {
        const startPt = getNodePortPosition(edge.source, edge.sourceHandle, true);
        const endPt = getNodePortPosition(edge.target, null, false);
        path.setAttribute("d", calculateBezierPath(startPt.x, startPt.y, endPt.x, endPt.y));
      }
    }
  });
}

function addNodeToCanvas(type) {
  if (!state.currentFlow) return;
  const id = `node_${Date.now()}`;
  const meta = NODE_META[type] || { title: type };

  // Center node in visible viewport
  const viewX = (-state.canvas.panX + 350) / state.canvas.scale;
  const viewY = (-state.canvas.panY + 250) / state.canvas.scale;

  const defaultData = {};
  if (type === "start") defaultData.trigger_type = "contains";
  if (type === "send_text") defaultData.message = "Hello! How can we help you?";
  if (type === "condition") {
    defaultData.field = "message.text";
    defaultData.operator = "equals";
    defaultData.value = "1";
  }
  if (type === "menu") {
    defaultData.message = "Please select an option:";
    defaultData.options = [
      { id: "opt_1", label: "Option 1", value: "1", pattern: "1" },
      { id: "opt_2", label: "Option 2", value: "2", pattern: "2" }
    ];
  }
  if (type === "delay") defaultData.seconds = 2;
  if (type === "wait_for_reply") defaultData.variable_name = "customer_reply";

  const newNode = {
    id,
    type,
    title: meta.title,
    position: { x: Math.round(viewX / 10) * 10, y: Math.round(viewY / 10) * 10 },
    data: defaultData
  };

  state.currentFlow.nodes.push(newNode);
  renderCanvas();
  selectNode(id);
  markUnsaved();
  showToast(`Added node: ${meta.title}`);
}

function addEdge(sourceId, targetId, handle = null) {
  if (!state.currentFlow) return;
  // Check if identical edge already exists
  const existing = (state.currentFlow.edges || []).find(e =>
    e.source === sourceId && e.target === targetId && e.sourceHandle === handle
  );
  if (existing) return;

  const edgeId = `e_${sourceId}_${targetId}_${handle || "default"}_${Date.now()}`;
  const newEdge = {
    id: edgeId,
    source: sourceId,
    target: targetId,
    sourceHandle: handle
  };

  state.currentFlow.edges.push(newEdge);
  renderCanvas();
  markUnsaved();
}

function deleteEdge(edgeId) {
  if (!state.currentFlow) return;
  state.currentFlow.edges = (state.currentFlow.edges || []).filter(e => e.id !== edgeId);
  renderCanvas();
  markUnsaved();
}

function deleteNode(nodeId) {
  if (!confirm("Delete this node and its connections?")) return;
  if (!state.currentFlow) return;
  state.currentFlow.nodes = (state.currentFlow.nodes || []).filter(n => n.id !== nodeId);
  state.currentFlow.edges = (state.currentFlow.edges || []).filter(e => e.source !== nodeId && e.target !== nodeId);
  renderCanvas();
  deselectNode();
  markUnsaved();
  showToast("Node deleted");
}

// -------------------------------------------------------------
// NODE CONFIGURATION INSPECTOR (RIGHT PANEL)
// -------------------------------------------------------------
function selectNode(nodeId) {
  state.selectedNodeId = nodeId;
  document.querySelectorAll(".flow-node").forEach(el => {
    el.classList.toggle("selected", el.id === `node-${nodeId}`);
  });

  const node = (state.currentFlow.nodes || []).find(n => n.id === nodeId);
  if (!node) {
    deselectNode();
    return;
  }

  const inspectorTitle = document.getElementById("inspectorTitle");
  const inspectorBody = document.getElementById("inspectorBody");
  inspectorTitle.textContent = `${node.title || node.type} Settings`;

  renderNodeInspector(node);
}

function deselectNode() {
  state.selectedNodeId = null;
  document.querySelectorAll(".flow-node").forEach(el => el.classList.remove("selected"));
  document.getElementById("inspectorTitle").textContent = "Node Settings";
  document.getElementById("inspectorBody").innerHTML = `
    <div class="empty-inspector">
      <i class="fa-solid fa-arrow-pointer text-muted"></i>
      <p>Select a node on the canvas to configure its settings</p>
    </div>
  `;
}

function renderNodeInspector(node) {
  const body = document.getElementById("inspectorBody");
  const d = node.data || {};
  let fieldsHtml = "";

  // Common: Node Title
  const titleField = `
    <div class="form-group">
      <label>Node Title</label>
      <input type="text" class="form-input" value="${escapeHtml(node.title || "")}" oninput="updateNodeTitle('${node.id}', this.value)">
    </div>
  `;

  // Specific form fields by node type
  if (node.type === "start") {
    fieldsHtml = `
      <div class="form-group">
        <label>Trigger Type</label>
        <select class="form-select" onchange="updateNodeData('${node.id}', 'trigger_type', this.value)">
          <option value="contains" ${d.trigger_type === "contains" ? "selected" : ""}>Contains Keyword</option>
          <option value="exact" ${d.trigger_type === "exact" ? "selected" : ""}>Exact Text Match</option>
          <option value="starts_with" ${d.trigger_type === "starts_with" ? "selected" : ""}>Starts With</option>
          <option value="ends_with" ${d.trigger_type === "ends_with" ? "selected" : ""}>Ends With</option>
          <option value="regex" ${d.trigger_type === "regex" ? "selected" : ""}>Regex Match</option>
          <option value="any" ${d.trigger_type === "any" ? "selected" : ""}>Any Incoming Message</option>
        </select>
      </div>
      <div class="form-group">
        <label>Trigger Values (comma-separated)</label>
        <input type="text" class="form-input" value="${escapeHtml(d.trigger_value || "")}" placeholder="e.g. hello, hi, support" oninput="updateNodeData('${node.id}', 'trigger_value', this.value)">
        <small class="form-hint">Matches against customer's incoming WhatsApp message.</small>
      </div>
    `;
  } else if (node.type === "send_text") {
    fieldsHtml = `
      <div class="form-group">
        <label>Message Content</label>
        <textarea id="nodeTextarea" class="form-input" rows="5" oninput="updateNodeData('${node.id}', 'message', this.value)">${escapeHtml(d.message || "")}</textarea>
        ${renderVariableHelpers("nodeTextarea")}
      </div>
    `;
  } else if (node.type === "condition") {
    fieldsHtml = `
      <div class="form-group">
        <label>Evaluate Field / Variable</label>
        <input type="text" class="form-input" value="${escapeHtml(d.field || "message.text")}" placeholder="message.text or variable_name" oninput="updateNodeData('${node.id}', 'field', this.value)">
        <small class="form-hint">e.g. message.text, contact.number, or conversation.product</small>
      </div>
      <div class="form-group">
        <label>Operator</label>
        <select class="form-select" onchange="updateNodeData('${node.id}', 'operator', this.value)">
          <option value="equals" ${d.operator === "equals" ? "selected" : ""}>Equals</option>
          <option value="not_equals" ${d.operator === "not_equals" ? "selected" : ""}>Not Equals</option>
          <option value="contains" ${d.operator === "contains" ? "selected" : ""}>Contains</option>
          <option value="not_contains" ${d.operator === "not_contains" ? "selected" : ""}>Does Not Contain</option>
          <option value="starts_with" ${d.operator === "starts_with" ? "selected" : ""}>Starts With</option>
          <option value="ends_with" ${d.operator === "ends_with" ? "selected" : ""}>Ends With</option>
          <option value="is_empty" ${d.operator === "is_empty" ? "selected" : ""}>Is Empty</option>
          <option value="is_not_empty" ${d.operator === "is_not_empty" ? "selected" : ""}>Is Not Empty</option>
          <option value="regex" ${d.operator === "regex" ? "selected" : ""}>Matches Regex</option>
        </select>
      </div>
      <div class="form-group">
        <label>Compare Value</label>
        <input type="text" class="form-input" value="${escapeHtml(d.value || "")}" placeholder="Value to match" oninput="updateNodeData('${node.id}', 'value', this.value)">
      </div>
      <div class="alert alert-info">
        Connect the <strong>YES</strong> port on the right for true, and <strong>NO</strong> for false.
      </div>
    `;
  } else if (node.type === "menu") {
    const options = d.options || [];
    fieldsHtml = `
      <div class="form-group">
        <label>Menu Prompt Message</label>
        <textarea id="nodeMenuTextarea" class="form-input" rows="4" oninput="updateNodeData('${node.id}', 'message', this.value)">${escapeHtml(d.message || "")}</textarea>
        ${renderVariableHelpers("nodeMenuTextarea")}
      </div>
      <div class="form-group">
        <div class="d-flex justify-content-between align-center mb-2">
          <label>Menu Choices</label>
          <button class="btn btn-sm btn-outline" onclick="addMenuOption('${node.id}')"><i class="fa-solid fa-plus"></i> Add Choice</button>
        </div>
        <div class="menu-options-list" style="display:flex; flex-direction:column; gap:8px;">
          ${options.map((opt, idx) => `
            <div class="card p-2" style="background:#f8fafc; border:1px solid #e2e8f0;">
              <div class="d-flex justify-content-between align-center mb-1">
                <strong>Choice #${idx + 1} (${opt.id})</strong>
                <button class="btn-icon text-danger" onclick="removeMenuOption('${node.id}', '${opt.id}')"><i class="fa-solid fa-trash"></i></button>
              </div>
              <input type="text" class="form-input mb-1" placeholder="Label: e.g. 1 - Sales" value="${escapeHtml(opt.label || "")}" oninput="updateMenuOption('${node.id}', '${opt.id}', 'label', this.value)">
              <input type="text" class="form-input" placeholder="Pattern: e.g. 1|sales" value="${escapeHtml(opt.pattern || opt.value || "")}" oninput="updateMenuOption('${node.id}', '${opt.id}', 'pattern', this.value)">
            </div>
          `).join("")}
        </div>
        <small class="form-hint mt-2">Each choice exposes a dedicated connector port on the right side of the node.</small>
      </div>
      <div class="alert alert-info mt-2">
        <strong><i class="fa-brands fa-whatsapp"></i> Customer WhatsApp Preview:</strong>
        <div style="white-space: pre-line; background: #efeae2; color: #111; padding: 8px; border-radius: 6px; margin-top: 6px; font-size: 12px; font-family: sans-serif;">
${escapeHtml(d.message || "Please choose:")}

${options.map((o, idx) => `*${o.value || idx + 1}* - ${o.label || o.value}`).join("\n")}
        </div>
      </div>
    `;
  } else if (node.type === "wait_for_reply") {
    fieldsHtml = `
      <div class="form-group">
        <label>Optional Prompt Message</label>
        <textarea class="form-input" rows="3" placeholder="e.g. Please type your full name:" oninput="updateNodeData('${node.id}', 'prompt_message', this.value)">${escapeHtml(d.prompt_message || "")}</textarea>
      </div>
      <div class="form-group">
        <label>Store Customer's Response in Variable</label>
        <input type="text" class="form-input" value="${escapeHtml(d.variable_name || "")}" placeholder="e.g. customer_name" oninput="updateNodeData('${node.id}', 'variable_name', this.value)">
        <small class="form-hint">Access this value later using {{conversation.variable_name}}</small>
      </div>
    `;
  } else if (node.type === "set_variable") {
    fieldsHtml = `
      <div class="form-group">
        <label>Variable Name</label>
        <input type="text" class="form-input" value="${escapeHtml(d.variable_name || "")}" placeholder="e.g. department" oninput="updateNodeData('${node.id}', 'variable_name', this.value)">
      </div>
      <div class="form-group">
        <label>Variable Value</label>
        <input type="text" id="setVarInput" class="form-input" value="${escapeHtml(d.variable_value || "")}" placeholder="e.g. Sales or {{message.text}}" oninput="updateNodeData('${node.id}', 'variable_value', this.value)">
        ${renderVariableHelpers("setVarInput")}
      </div>
    `;
  } else if (node.type === "send_image") {
    fieldsHtml = `
      <div class="form-group">
        <label>Image URL *</label>
        <input type="text" class="form-input" value="${escapeHtml(d.image_url || "")}" placeholder="https://example.com/photo.jpg" oninput="updateNodeData('${node.id}', 'image_url', this.value)">
      </div>
      <div class="form-group">
        <label>Caption</label>
        <textarea id="imgCaption" class="form-input" rows="3" oninput="updateNodeData('${node.id}', 'caption', this.value)">${escapeHtml(d.caption || "")}</textarea>
        ${renderVariableHelpers("imgCaption")}
      </div>
    `;
  } else if (node.type === "send_file") {
    fieldsHtml = `
      <div class="form-group">
        <label>File / Document URL *</label>
        <input type="text" class="form-input" value="${escapeHtml(d.file_url || "")}" placeholder="https://example.com/catalog.pdf" oninput="updateNodeData('${node.id}', 'file_url', this.value)">
      </div>
      <div class="form-group">
        <label>Filename (Optional)</label>
        <input type="text" class="form-input" value="${escapeHtml(d.filename || "")}" placeholder="Catalog.pdf" oninput="updateNodeData('${node.id}', 'filename', this.value)">
      </div>
      <div class="form-group">
        <label>Caption (Optional)</label>
        <input type="text" class="form-input" value="${escapeHtml(d.caption || "")}" oninput="updateNodeData('${node.id}', 'caption', this.value)">
      </div>
    `;
  } else if (node.type === "delay") {
    fieldsHtml = `
      <div class="form-group">
        <label>Delay Duration (1 to 10 Seconds)</label>
        <input type="number" class="form-input" min="1" max="10" value="${d.seconds || 2}" oninput="updateNodeData('${node.id}', 'seconds', parseInt(this.value)||2)">
        <small class="form-hint">Pauses flow execution before sending the next message.</small>
      </div>
    `;
  } else if (node.type === "http_request") {
    fieldsHtml = `
      <div class="form-group">
        <label>Method</label>
        <select class="form-select" onchange="updateNodeData('${node.id}', 'method', this.value)">
          <option value="POST" ${d.method === "POST" ? "selected" : ""}>POST</option>
          <option value="GET" ${d.method === "GET" ? "selected" : ""}>GET</option>
          <option value="PUT" ${d.method === "PUT" ? "selected" : ""}>PUT</option>
          <option value="DELETE" ${d.method === "DELETE" ? "selected" : ""}>DELETE</option>
        </select>
      </div>
      <div class="form-group">
        <label>API Endpoint URL</label>
        <input type="text" class="form-input" value="${escapeHtml(d.url || "")}" placeholder="http://192.168.100.50/api/customer" oninput="updateNodeData('${node.id}', 'url', this.value)">
      </div>
      <div class="form-group">
        <label>JSON Body (Variables allowed)</label>
        <textarea class="form-input code-font" rows="3" placeholder='{"phone": "{{contact.number}}"}' oninput="updateNodeData('${node.id}', 'body', this.value)">${escapeHtml(d.body || "")}</textarea>
      </div>
      <div class="form-group">
        <label>Store Response in Variable</label>
        <input type="text" class="form-input" value="${escapeHtml(d.response_variable || "")}" placeholder="e.g. api_result" oninput="updateNodeData('${node.id}', 'response_variable', this.value)">
      </div>
    `;
  } else if (node.type === "human_handoff") {
    fieldsHtml = `
      <div class="form-group">
        <label>Notification to Customer</label>
        <textarea class="form-input" rows="3" placeholder="e.g. Connecting you with our support agent now..." oninput="updateNodeData('${node.id}', 'notify_message', this.value)">${escapeHtml(d.notify_message || "")}</textarea>
        <small class="form-hint">Pauses bot automation for this customer until an admin clicks "Resume Bot".</small>
      </div>
    `;
  } else if (node.type === "end") {
    fieldsHtml = `
      <div class="alert alert-info">
        This node ends the flow execution and marks the conversation as completed.
      </div>
    `;
  }

  body.innerHTML = `
    ${titleField}
    ${fieldsHtml}
    <div class="mt-4 pt-3" style="border-top: 1px solid var(--border);">
      <button class="btn btn-outline text-danger w-full" onclick="deleteNode('${node.id}')"><i class="fa-solid fa-trash"></i> Delete Node</button>
    </div>
  `;
}

function renderVariableHelpers(targetInputId) {
  return `
    <div class="variable-helpers">
      <span class="var-pill" onclick="insertVariable('${targetInputId}', '{{contact.name}}')">{{contact.name}}</span>
      <span class="var-pill" onclick="insertVariable('${targetInputId}', '{{contact.number}}')">{{contact.number}}</span>
      <span class="var-pill" onclick="insertVariable('${targetInputId}', '{{message.text}}')">{{message.text}}</span>
      <span class="var-pill" onclick="insertVariable('${targetInputId}', '{{conversation.variableName}}')">{{conversation.var}}</span>
    </div>
  `;
}

function insertVariable(inputId, placeholder) {
  const el = document.getElementById(inputId);
  if (!el) return;
  const start = el.selectionStart || el.value.length;
  const end = el.selectionEnd || el.value.length;
  el.value = el.value.substring(0, start) + placeholder + el.value.substring(end);
  el.focus();
  el.selectionStart = el.selectionEnd = start + placeholder.length;
  el.dispatchEvent(new Event("input"));
}

function updateNodeTitle(nodeId, newTitle) {
  const node = (state.currentFlow.nodes || []).find(n => n.id === nodeId);
  if (!node) return;
  node.title = newTitle;
  const titleEl = document.querySelector(`#node-${nodeId} .node-header-title span`);
  if (titleEl) titleEl.textContent = newTitle;
  markUnsaved();
}

function updateNodeData(nodeId, field, value) {
  const node = (state.currentFlow.nodes || []).find(n => n.id === nodeId);
  if (!node) return;
  if (!node.data) node.data = {};
  node.data[field] = value;

  // Re-render node card to update preview
  const oldEl = document.getElementById(`node-${nodeId}`);
  if (oldEl) {
    const newEl = createNodeElement(node);
    oldEl.parentNode.replaceChild(newEl, oldEl);
  }
  markUnsaved();
}

function addMenuOption(nodeId) {
  const node = (state.currentFlow.nodes || []).find(n => n.id === nodeId);
  if (!node) return;
  if (!node.data) node.data = {};
  if (!node.data.options) node.data.options = [];
  const nextNum = node.data.options.length + 1;
  node.data.options.push({
    id: `opt_${Date.now()}`,
    label: `Option ${nextNum}`,
    value: `${nextNum}`,
    pattern: `${nextNum}`
  });
  renderCanvas();
  selectNode(nodeId);
  markUnsaved();
}

function updateMenuOption(nodeId, optId, key, val) {
  const node = (state.currentFlow.nodes || []).find(n => n.id === nodeId);
  if (!node || !node.data || !node.data.options) return;
  const opt = node.data.options.find(o => o.id === optId);
  if (!opt) return;
  opt[key] = val;
  markUnsaved();
}

function removeMenuOption(nodeId, optId) {
  const node = (state.currentFlow.nodes || []).find(n => n.id === nodeId);
  if (!node || !node.data || !node.data.options) return;
  node.data.options = node.data.options.filter(o => o.id !== optId);
  // Also delete edges using this handle
  state.currentFlow.edges = (state.currentFlow.edges || []).filter(e => !(e.source === nodeId && e.sourceHandle === optId));
  renderCanvas();
  selectNode(nodeId);
  markUnsaved();
}

// -------------------------------------------------------------
// SAVE & AUTOSAVE
// -------------------------------------------------------------
function setSaveStatus(status) {
  const ind = document.getElementById("saveStatusIndicator");
  if (status === "Saving...") {
    ind.innerHTML = `<i class="fa-solid fa-spinner fa-spin text-blue"></i> <span>Saving...</span>`;
  } else if (status === "Unsaved changes") {
    ind.innerHTML = `<i class="fa-solid fa-circle-dot text-yellow"></i> <span>Unsaved changes</span>`;
  } else {
    ind.innerHTML = `<i class="fa-solid fa-circle-check text-green"></i> <span>Saved</span>`;
  }
}

function markUnsaved() {
  state.hasUnsavedChanges = true;
  setSaveStatus("Unsaved changes");

  clearTimeout(state.autosaveTimer);
  state.autosaveTimer = setTimeout(() => {
    saveCurrentFlow(false);
  }, 2000);
}

async function saveCurrentFlow(manual = true) {
  if (!state.currentFlow) return;
  clearTimeout(state.autosaveTimer);
  setSaveStatus("Saving...");

  const flowId = state.currentFlow.id;
  const name = document.getElementById("builderFlowName").value.trim() || state.currentFlow.name;
  const priority = parseInt(document.getElementById("builderFlowPriority").value) || 100;
  const isDefault = document.getElementById("builderFlowIsDefault").checked ? 1 : 0;
  const enabled = document.getElementById("builderFlowEnabled").checked ? 1 : 0;

  // Extract trigger from Start node if present
  let triggerType = state.currentFlow.trigger_type || "contains";
  let triggerValue = state.currentFlow.trigger_value || "";
  const startNode = (state.currentFlow.nodes || []).find(n => n.type === "start");
  if (startNode && startNode.data) {
    if (startNode.data.trigger_type) triggerType = startNode.data.trigger_type;
    if (startNode.data.trigger_value !== undefined) triggerValue = startNode.data.trigger_value;
  }

  const payload = {
    name,
    description: state.currentFlow.description || "",
    enabled,
    priority,
    is_default: isDefault,
    trigger_type: triggerType,
    trigger_value: triggerValue,
    nodes_json: JSON.stringify(state.currentFlow.nodes || []),
    edges_json: JSON.stringify(state.currentFlow.edges || [])
  };

  try {
    const resp = await fetch(`${API_BASE}/api/flows/${flowId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    if (resp.ok) {
      const data = await resp.json();
      state.currentFlow.version = data.version;
      document.getElementById("builderFlowVersion").textContent = `v${data.version}`;
      state.hasUnsavedChanges = false;
      setSaveStatus("Saved");
      if (manual) showToast("Flow saved successfully!");
    } else {
      setSaveStatus("Unsaved changes");
      if (manual) showToast("Error saving flow", true);
    }
  } catch (e) {
    setSaveStatus("Unsaved changes");
    if (manual) showToast("Failed to connect to backend", true);
  }
}

// -------------------------------------------------------------
// FLOW VALIDATION
// -------------------------------------------------------------
async function validateCurrentFlow() {
  if (!state.currentFlow) return;
  await saveCurrentFlow(false);
  try {
    const resp = await fetch(`${API_BASE}/api/flows/${state.currentFlow.id}/validate`, { method: "POST" });
    if (!resp.ok) return;
    const res = await resp.json();

    if (res.valid && res.warnings.length === 0) {
      alert("✅ Flow Validation Passed!\nAll nodes are properly configured and connected.");
    } else {
      let msg = res.valid ? "⚠️ Flow has warnings:\n" : "❌ Flow Validation Failed:\n";
      if (res.errors.length) {
        msg += "\nErrors:\n" + res.errors.map(e => `• ${e}`).join("\n");
      }
      if (res.warnings.length) {
        msg += "\nWarnings:\n" + res.warnings.map(w => `• ${w}`).join("\n");
      }
      alert(msg);
    }
  } catch (e) {
    showToast("Validation failed", true);
  }
}

// -------------------------------------------------------------
// IN-MEMORY SIMULATOR
// -------------------------------------------------------------
function openSimulatorModal() {
  if (!state.currentFlow) return;
  resetSimulator();
  openModal("simulatorModal");
}

function resetSimulator() {
  state.simSession = {
    status: "idle",
    waitingNodeId: null,
    variables: {},
    trace: []
  };
  document.getElementById("simStatusTag").textContent = "Idle";
  document.getElementById("simStatusTag").className = "badge badge-gray";
  document.getElementById("simWaitingNode").textContent = "None";
  document.getElementById("simVariablesJson").textContent = "{}";
  document.getElementById("simTraceStream").innerHTML = `<div class="text-muted text-center p-4">Simulation session reset. Enter a message and click "Run".</div>`;

  // Clear canvas visual highlights
  document.querySelectorAll(".flow-node").forEach(el => el.classList.remove("sim-active"));
}

async function runSimulationStep() {
  if (!state.currentFlow) return;
  const msgInput = document.getElementById("simMessageInput");
  const msg = msgInput.value.trim();
  if (!msg) return;

  const contactName = document.getElementById("simContactName").value.trim() || "Ahmed";
  const contactNumber = document.getElementById("simContactNumber").value.trim() || "201281102350";

  msgInput.value = "";

  try {
    const resp = await fetch(`${API_BASE}/api/flows/${state.currentFlow.id}/test`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: msg,
        resume_node_id: state.simSession.waitingNodeId,
        contact_name: contactName,
        contact_number: contactNumber,
        variables: state.simSession.variables
      })
    });

    if (!resp.ok) {
      showToast("Simulation error", true);
      return;
    }

    const res = await resp.json();
    state.simSession.status = res.status;
    state.simSession.waitingNodeId = res.status === "waiting_for_reply" ? res.current_node_id : null;
    state.simSession.variables = res.variables || {};

    // Update Status Box
    const statusTag = document.getElementById("simStatusTag");
    statusTag.textContent = res.status;
    statusTag.className = `badge ${res.status === 'completed' ? 'badge-green' : res.status === 'waiting_for_reply' ? 'badge-blue' : 'badge-yellow'}`;
    document.getElementById("simWaitingNode").textContent = res.current_node_id || "None";
    document.getElementById("simVariablesJson").textContent = JSON.stringify(res.variables, null, 2);

    // Append to Trace Stream
    renderSimulationTrace(msg, res.trace);

    // Highlight active nodes on canvas
    document.querySelectorAll(".flow-node").forEach(el => el.classList.remove("sim-active"));
    (res.trace || []).forEach(step => {
      if (step.node_id) {
        const el = document.getElementById(`node-${step.node_id}`);
        if (el) el.classList.add("sim-active");
      }
    });
  } catch (e) {
    showToast("Failed to run simulation", true);
  }
}

function renderSimulationTrace(userMsg, traceSteps) {
  const container = document.getElementById("simTraceStream");
  const existingEmpty = container.querySelector(".text-muted");
  if (existingEmpty) container.innerHTML = "";

  let html = `<div class="sim-step-item" style="border-left: 3px solid var(--primary); background:#eff6ff;">
    <strong>Customer:</strong> "${escapeHtml(userMsg)}"
  </div>`;

  (traceSteps || []).forEach(s => {
    let actionBadge = `<span class="badge badge-gray">${escapeHtml(s.action || "")}</span>`;
    let detail = "";
    if (s.message) detail = `<div class="mt-1"><strong>Bot:</strong> "${escapeHtml(s.message)}"</div>`;
    if (s.variable) detail = `<div class="mt-1 text-green">Set {{${s.variable}}} = "${escapeHtml(s.value)}"</div>`;
    if (s.result !== undefined) detail = `<div class="mt-1">Evaluated Condition -> <strong>${s.result ? 'YES' : 'NO'}</strong></div>`;
    if (s.option_id) detail = `<div class="mt-1">Matched Option: <strong>${escapeHtml(s.option_id)}</strong></div>`;

    html += `
      <div class="sim-step-item">
        <div class="d-flex justify-content-between align-center">
          <strong>${escapeHtml(s.title || s.type || "Node")}</strong>
          ${actionBadge}
        </div>
        ${detail}
      </div>
    `;
  });

  container.innerHTML += html;
  container.scrollTop = container.scrollHeight;
}

// -------------------------------------------------------------
// LIVE WHATSAPP TEST
// -------------------------------------------------------------
function openLiveTestModal() {
  document.getElementById("liveTestResultBox").style.display = "none";
  openModal("liveTestModal");
}

async function sendLiveTest() {
  if (!state.currentFlow) return;
  const num = document.getElementById("liveTestNumber").value.trim();
  const msg = document.getElementById("liveTestMessage").value.trim();
  if (!num || !msg) {
    alert("Please enter both a WhatsApp phone number and a test message.");
    return;
  }

  const btn = document.getElementById("btnSendLiveTest");
  btn.disabled = true;
  btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Sending...`;

  try {
    const resp = await fetch(`${API_BASE}/api/flows/${state.currentFlow.id}/live-test`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ number: num, message: msg })
    });
    const res = await resp.json();
    document.getElementById("liveTestResultBox").style.display = "block";
    document.getElementById("liveTestResultJson").textContent = JSON.stringify(res, null, 2);
    showToast("Live test executed!");
  } catch (e) {
    showToast("Live test failed", true);
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<i class="fa-solid fa-paper-plane"></i> Send Test`;
  }
}

// -------------------------------------------------------------
// VERSIONS HISTORY
// -------------------------------------------------------------
async function openVersionsModal() {
  if (!state.currentFlow) return;
  const list = document.getElementById("versionsList");
  list.innerHTML = `<div class="loading-spinner"><i class="fa-solid fa-spinner fa-spin"></i> Loading versions...</div>`;
  openModal("versionsModal");

  try {
    const resp = await fetch(`${API_BASE}/api/flows/${state.currentFlow.id}/versions`);
    if (!resp.ok) return;
    const versions = await resp.json();

    if (!versions.length) {
      list.innerHTML = `<div class="text-center text-muted p-4">No version snapshots found.</div>`;
      return;
    }

    list.innerHTML = versions.map(v => `
      <div class="dash-item">
        <div class="dash-item-info">
          <span class="dash-item-title">Version ${v.version}</span>
          <span class="dash-item-sub">Saved at: ${v.created_at} • Priority: ${v.priority}</span>
        </div>
        <button class="btn btn-sm btn-outline" onclick="restoreVersion(${v.version})"><i class="fa-solid fa-rotate-left"></i> Restore</button>
      </div>
    `).join("");
  } catch (e) {
    list.innerHTML = `<div class="text-center text-danger p-4">Error loading versions.</div>`;
  }
}

async function restoreVersion(v) {
  if (!confirm(`Restore Version ${v}? Any unsaved changes will be replaced.`)) return;
  try {
    const resp = await fetch(`${API_BASE}/api/flows/${state.currentFlow.id}/versions/${v}/restore`, { method: "POST" });
    if (resp.ok) {
      closeModal("versionsModal");
      showToast(`Restored version ${v}`);
      openFlowEditor(state.currentFlow.id);
    }
  } catch (e) {
    showToast("Restore failed", true);
  }
}

// -------------------------------------------------------------
// EXPORT FLOW
// -------------------------------------------------------------
async function exportCurrentFlow() {
  if (!state.currentFlow) return;
  await saveCurrentFlow(false);
  window.open(`${API_BASE}/api/flows/${state.currentFlow.id}/export`, "_blank");
}

function exportFlow(flowId) {
  window.open(`${API_BASE}/api/flows/${flowId}/export`, "_blank");
}

// -------------------------------------------------------------
// CONTACTS PAGE
// -------------------------------------------------------------
let contactSearchDebounce = null;

function debounceContactSearch() {
  clearTimeout(contactSearchDebounce);
  contactSearchDebounce = setTimeout(loadContacts, 300);
}

async function loadContacts() {
  const tbody = document.getElementById("contactsTableBody");
  const q = (document.getElementById("contactSearchInput").value || "").trim();
  tbody.innerHTML = `<tr><td colspan="6" class="text-center p-4"><i class="fa-solid fa-spinner fa-spin"></i> Loading contacts...</td></tr>`;

  try {
    const url = q ? `${API_BASE}/api/contacts?q=${encodeURIComponent(q)}` : `${API_BASE}/api/contacts`;
    const resp = await fetch(url);
    if (!resp.ok) return;
    const contacts = await resp.json();

    if (!contacts.length) {
      tbody.innerHTML = `<tr><td colspan="6" class="text-center p-4">No contacts found. Click "Sync from WAHA" to fetch contacts.</td></tr>`;
      return;
    }

    tbody.innerHTML = contacts.map(c => `
      <tr>
        <td><strong>${escapeHtml(c.name || c.push_name || "Unknown")}</strong></td>
        <td><span class="code-font">+${escapeHtml(c.id)}</span></td>
        <td><small class="text-muted">${escapeHtml(c.lid || "-")}</small></td>
        <td>
          <label class="switch switch-sm" title="${c.bot_disabled ? 'Bot Disabled for Human Takeover' : 'Bot Enabled'}">
            <input type="checkbox" ${!c.bot_disabled ? "checked" : ""} onchange="toggleContactBot('${c.id}')">
            <span class="slider round"></span>
          </label>
          <span class="ml-2 ${c.bot_disabled ? 'text-danger' : 'text-green'}" style="font-size:12px; font-weight:600;">
            ${c.bot_disabled ? "Human Takeover" : "Bot Active"}
          </span>
        </td>
        <td><small class="text-muted">${c.last_seen}</small></td>
        <td class="text-right">
          <button class="btn btn-sm btn-outline" onclick="openConversationForContact('${c.id}')"><i class="fa-solid fa-comments"></i> Chat</button>
        </td>
      </tr>
    `).join("");
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="6" class="text-center text-danger p-4">Error loading contacts.</td></tr>`;
  }
}

async function toggleContactBot(contactId) {
  try {
    const resp = await fetch(`${API_BASE}/api/contacts/${contactId}/toggle-bot`, { method: "PUT" });
    if (resp.ok) {
      showToast("Contact bot automation status updated");
      loadContacts();
    }
  } catch (e) {
    showToast("Failed to update contact", true);
  }
}

async function syncContacts() {
  try {
    const resp = await fetch(`${API_BASE}/api/contacts/sync`, { method: "POST" });
    if (resp.ok) {
      showToast("Contacts sync started in background. Refreshing list in 3s...");
      setTimeout(loadContacts, 3000);
    }
  } catch (e) {
    showToast("Sync failed", true);
  }
}

function openConversationForContact(contactId) {
  switchPage("conversations");
  selectConversation(contactId);
}

// -------------------------------------------------------------
// CONVERSATIONS PAGE
// -------------------------------------------------------------
let convFilter = "all";

function filterConversations(tab) {
  convFilter = tab;
  document.querySelectorAll(".filter-tabs .tab-btn").forEach(btn => {
    btn.classList.toggle("active", btn.textContent.toLowerCase().includes(tab.replace("_", " ")));
  });
  loadConversations();
}

async function loadConversations() {
  const container = document.getElementById("conversationsList");
  container.innerHTML = `<div class="loading-spinner"><i class="fa-solid fa-spinner fa-spin"></i> Loading conversations...</div>`;

  try {
    const url = convFilter !== "all" ? `${API_BASE}/api/conversations?status=${convFilter}` : `${API_BASE}/api/conversations`;
    const resp = await fetch(url);
    if (!resp.ok) return;
    const convs = await resp.json();

    if (!convs.length) {
      container.innerHTML = `<div class="text-center text-muted p-4">No active conversations found.</div>`;
      return;
    }

    container.innerHTML = convs.map(c => {
      let badgeClass = "badge-gray";
      if (c.status === "active") badgeClass = "badge-blue";
      if (c.status === "waiting_for_reply") badgeClass = "badge-purple";
      if (c.status === "human_mode") badgeClass = "badge-yellow";

      return `
        <div class="conv-item ${state.activeConversationId === c.contact_id ? "active" : ""}" onclick="selectConversation('${c.contact_id}')">
          <div class="conv-item-top">
            <span class="conv-item-name">${escapeHtml(c.contact_name || c.contact_id)}</span>
            <span class="conv-item-time">${c.updated_at ? c.updated_at.split(" ")[1] : ""}</span>
          </div>
          <div class="conv-item-number">+${escapeHtml(c.contact_id)}</div>
          <div class="conv-item-bottom">
            <span class="badge ${badgeClass}">${escapeHtml(c.status.replace("_", " "))}</span>
            <span class="text-muted" style="font-size:11px;">${escapeHtml(c.flow_name || "No Flow")}</span>
          </div>
        </div>
      `;
    }).join("");
  } catch (e) {
    container.innerHTML = `<div class="text-center text-danger p-4">Error loading conversations.</div>`;
  }
}

async function selectConversation(contactId) {
  state.activeConversationId = contactId;
  document.querySelectorAll(".conv-item").forEach(el => {
    el.classList.toggle("active", el.innerHTML.includes(`+${contactId}`));
  });

  const emptyState = document.getElementById("convEmptyState");
  const content = document.getElementById("convContent");
  emptyState.style.display = "none";
  content.style.display = "flex";

  try {
    const resp = await fetch(`${API_BASE}/api/conversations/${contactId}`);
    if (!resp.ok) return;
    const data = await resp.json();

    // Contact Details Header
    const c = data.contact || {};
    const conv = data.conversation || {};
    document.getElementById("convContactName").textContent = c.name || c.push_name || contactId;
    document.getElementById("convContactNumber").textContent = `+${contactId}`;

    const statusBadge = document.getElementById("convStatusBadge");
    const st = conv.status || "idle";
    statusBadge.textContent = st.replace("_", " ");
    statusBadge.className = `badge ${st === 'human_mode' ? 'badge-yellow' : st === 'waiting_for_reply' ? 'badge-purple' : 'badge-green'}`;

    // Resume button visibility
    const btnResume = document.getElementById("btnResumeBot");
    btnResume.style.display = (st === "human_mode" || c.bot_disabled) ? "inline-flex" : "none";

    // Variables Box
    const varsContainer = document.getElementById("convVariablesList");
    const vars = data.variables || {};
    if (Object.keys(vars).length === 0) {
      varsContainer.innerHTML = `<span class="text-muted" style="font-size:12px;">No custom variables stored yet.</span>`;
    } else {
      varsContainer.innerHTML = Object.entries(vars).map(([k, v]) => `
        <span class="badge badge-gray" style="font-family:monospace;">${escapeHtml(k)}: "${escapeHtml(v)}"</span>
      `).join("");
    }

    // Message History Transcript
    renderChatTranscript(data.history || []);
  } catch (e) {
    showToast("Error loading conversation detail", true);
  }
}

function renderChatTranscript(logs) {
  const container = document.getElementById("chatTranscript");
  if (!logs.length) {
    container.innerHTML = `<div class="text-center text-muted p-4">No message logs recorded for this contact.</div>`;
    return;
  }

  container.innerHTML = logs.map(l => {
    if (l.direction === "incoming") {
      return `
        <div class="chat-bubble chat-incoming">
          <div>${escapeHtml(l.message_text || "")}</div>
          <div class="chat-meta">${l.timestamp.split(" ")[1] || l.timestamp}</div>
        </div>
      `;
    } else if (l.direction === "outgoing") {
      const isAgent = l.event_type === "agent_reply" || (l.details && l.details.includes("agent"));
      return `
        <div class="chat-bubble ${isAgent ? 'chat-agent' : 'chat-outgoing'}">
          ${isAgent ? '<span class="agent-badge"><i class="fa-solid fa-user-tie"></i> Agent</span>' : ''}
          <div>${escapeHtml(l.message_text || "")}</div>
          <div class="chat-meta">${l.timestamp.split(" ")[1] || l.timestamp} <i class="fa-solid fa-check-double text-blue ml-1"></i></div>
        </div>
      `;
    } else {
      return `
        <div class="chat-system">
          <i class="fa-solid fa-gear"></i> ${escapeHtml(l.event_type)}: ${escapeHtml(l.message_text || "")}
        </div>
      `;
    }
  }).join("");

  container.scrollTop = container.scrollHeight;
}

async function sendAgentReply() {
  if (!state.activeConversationId) return;
  const input = document.getElementById("agentReplyInput");
  const text = (input.value || "").trim();
  if (!text) return;

  const btn = document.getElementById("btnSendAgentReply");
  btn.disabled = true;
  btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i>`;

  try {
    const resp = await fetch(`${API_BASE}/api/conversations/${state.activeConversationId}/send`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text })
    });

    if (resp.ok) {
      input.value = "";
      input.style.height = "auto";
      await selectConversation(state.activeConversationId);
      loadConversations();
      showToast("Message sent to customer via WhatsApp!");
    } else {
      const err = await resp.json();
      showToast(err.detail || "Failed to send message", true);
    }
  } catch (e) {
    showToast("Error connecting to server", true);
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<i class="fa-solid fa-paper-plane"></i> Send`;
  }
}

function handleAgentReplyKey(event) {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendAgentReply();
  }
}

function setupConversationPolling() {
  setInterval(async () => {
    if (state.currentPage === "conversations" && state.activeConversationId) {
      try {
        const resp = await fetch(`${API_BASE}/api/conversations/${state.activeConversationId}`);
        if (!resp.ok) return;
        const data = await resp.json();
        const currentBubbleCount = document.querySelectorAll("#chatTranscript .chat-bubble, #chatTranscript .chat-system").length;
        const newLogsCount = (data.history || []).length;
        if (newLogsCount !== currentBubbleCount) {
          renderChatTranscript(data.history || []);
          const conv = data.conversation || {};
          const statusBadge = document.getElementById("convStatusBadge");
          const st = conv.status || "idle";
          statusBadge.textContent = st.replace("_", " ");
          statusBadge.className = `badge ${st === 'human_mode' ? 'badge-yellow' : st === 'waiting_for_reply' ? 'badge-purple' : 'badge-green'}`;
          const btnResume = document.getElementById("btnResumeBot");
          const c = data.contact || {};
          btnResume.style.display = (st === "human_mode" || c.bot_disabled) ? "inline-flex" : "none";
        }
      } catch (e) {
        // silent
      }
    }
  }, 3000);
}

async function resumeCurrentConversationBot() {
  if (!state.activeConversationId) return;
  try {
    const resp = await fetch(`${API_BASE}/api/conversations/${state.activeConversationId}/resume`, { method: "POST" });
    if (resp.ok) {
      showToast("Bot automation resumed for contact!");
      selectConversation(state.activeConversationId);
      loadConversations();
    }
  } catch (e) {
    showToast("Failed to resume bot", true);
  }
}

async function resetCurrentConversation() {
  if (!state.activeConversationId) return;
  if (!confirm("Reset active flow position and clear current waiting state?")) return;
  try {
    const resp = await fetch(`${API_BASE}/api/conversations/${state.activeConversationId}/reset`, { method: "POST" });
    if (resp.ok) {
      showToast("Conversation flow reset to idle");
      selectConversation(state.activeConversationId);
      loadConversations();
    }
  } catch (e) {
    showToast("Failed to reset conversation", true);
  }
}

// -------------------------------------------------------------
// LOGS PAGE
// -------------------------------------------------------------
let logsSearchDebounce = null;
function debounceLogsSearch() {
  clearTimeout(logsSearchDebounce);
  logsSearchDebounce = setTimeout(loadLogs, 300);
}

async function loadLogs() {
  const tbody = document.getElementById("logsTableBody");
  tbody.innerHTML = `<tr><td colspan="5" class="text-center p-4"><i class="fa-solid fa-spinner fa-spin"></i> Loading logs...</td></tr>`;

  const direction = document.getElementById("logFilterDirection").value;
  const eventType = document.getElementById("logFilterEvent").value;
  const contact = (document.getElementById("logFilterContact").value || "").trim();

  let queryParams = new URLSearchParams();
  if (direction) queryParams.append("direction", direction);
  if (eventType) queryParams.append("event_type", eventType);
  if (contact) queryParams.append("contact_id", contact);

  try {
    const resp = await fetch(`${API_BASE}/api/logs?${queryParams.toString()}`);
    if (!resp.ok) return;
    const logs = await resp.json();

    if (!logs.length) {
      tbody.innerHTML = `<tr><td colspan="5" class="text-center p-4">No logs found matching criteria.</td></tr>`;
      return;
    }

    tbody.innerHTML = logs.map(l => {
      let dirBadge = "badge-gray";
      if (l.direction === "incoming") dirBadge = "badge-green";
      if (l.direction === "outgoing") dirBadge = "badge-blue";
      if (l.direction === "error") dirBadge = "badge-red";
      if (l.direction === "system") dirBadge = "badge-purple";

      return `
        <tr>
          <td><small class="text-muted">${l.timestamp}</small></td>
          <td><span class="badge ${dirBadge}">${l.direction}</span></td>
          <td>${l.contact_id ? `<span class="code-font">+${escapeHtml(l.contact_id)}</span>` : '<span class="text-muted">-</span>'}</td>
          <td><strong>${escapeHtml(l.event_type)}</strong></td>
          <td>
            <div>${escapeHtml(l.message_text || "")}</div>
            ${l.details ? `<pre class="code-font text-muted mt-1" style="font-size:11px;">${escapeHtml(l.details)}</pre>` : ""}
          </td>
        </tr>
      `;
    }).join("");
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="5" class="text-center text-danger p-4">Error loading logs.</td></tr>`;
  }
}

async function clearAllLogs() {
  if (!confirm("Are you sure you want to clear all log history?")) return;
  try {
    const resp = await fetch(`${API_BASE}/api/logs`, { method: "DELETE" });
    if (resp.ok) {
      showToast("Logs cleared");
      loadLogs();
    }
  } catch (e) {
    showToast("Failed to clear logs", true);
  }
}

// -------------------------------------------------------------
// SETTINGS PAGE
// -------------------------------------------------------------
async function loadSettings() {
  try {
    const resp = await fetch(`${API_BASE}/api/settings`);
    if (!resp.ok) return;
    const data = await resp.json();

    const s = data.settings || {};
    document.getElementById("settingsMaxSteps").value = s.max_execution_steps || 50;
    document.getElementById("settingsGroupMode").value = s.group_mode || "mentions_only";
    document.getElementById("settingsWahaUrl").textContent = data.waha_url;
    document.getElementById("settingsWahaSession").textContent = data.session_name;

    const stBadge = document.getElementById("settingsWahaStatus");
    stBadge.textContent = data.session_status || "UNKNOWN";
    stBadge.className = `badge ${data.session_status === 'WORKING' ? 'badge-green' : 'badge-yellow'}`;

    // Populate default flows dropdown
    const flowsResp = await fetch(`${API_BASE}/api/flows`);
    if (flowsResp.ok) {
      const flows = await flowsResp.json();
      const select = document.getElementById("settingsDefaultFlow");
      select.innerHTML = `<option value="">-- No Default Fallback --</option>` + flows.map(f => `
        <option value="${f.id}" ${String(s.default_flow_id) === String(f.id) || f.is_default ? "selected" : ""}>
          ${escapeHtml(f.name)} (${f.trigger_type}: ${escapeHtml(f.trigger_value || "*")})
        </option>
      `).join("");
    }
  } catch (e) {
    showToast("Error loading settings", true);
  }
}

async function saveSettings() {
  const defaultFlowId = document.getElementById("settingsDefaultFlow").value;
  const maxSteps = document.getElementById("settingsMaxSteps").value;
    const groupMode = document.getElementById("settingsGroupMode").value;
  try {
    const resp = await fetch(`${API_BASE}/api/settings`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        default_flow_id: defaultFlowId,
        max_execution_steps: maxSteps,
        group_mode: groupMode,
        ignore_groups: groupMode === "disabled" ? "true" : "false"
      })
    });
    if (resp.ok) {
      showToast("Settings saved successfully!");
    }
  } catch (e) {
    showToast("Failed to save settings", true);
  }
}

// -------------------------------------------------------------
// MODALS & UTILS
// -------------------------------------------------------------
function openModal(id) {
  document.getElementById(id).classList.add("active");
}

function closeModal(id) {
  document.getElementById(id).classList.remove("active");
}

function escapeHtml(text) {
  if (!text) return "";
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
