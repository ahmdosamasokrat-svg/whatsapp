import re
import json
import time
import asyncio
import requests
from typing import Dict, Any, List, Optional, Tuple
from database import get_db, now_iso
import waha


def get_setting(key: str, default: str = "") -> str:
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT value FROM bot_settings WHERE key = ?", (key,))
        row = cur.fetchone()
        return row["value"] if row else default
    finally:
        conn.close()


def set_setting(key: str, value: str):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("INSERT OR REPLACE INTO bot_settings (key, value) VALUES (?, ?)", (key, value))
        conn.commit()
    finally:
        conn.close()


def log_event(
    direction: str,
    event_type: str,
    contact_id: Optional[str] = None,
    flow_id: Optional[int] = None,
    node_id: Optional[str] = None,
    message_text: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None
):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO message_logs (timestamp, direction, contact_id, flow_id, node_id, event_type, message_text, details)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            now_iso(),
            direction,
            contact_id,
            flow_id,
            node_id,
            event_type,
            message_text,
            json.dumps(details, ensure_ascii=False) if details else None
        ))
        conn.commit()
    except Exception as e:
        print(f"[Log Error] {e}")
    finally:
        conn.close()


def get_contact_variables(contact_id: str) -> Dict[str, str]:
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT key, value FROM conversation_variables WHERE contact_id = ?", (contact_id,))
        rows = cur.fetchall()
        return {r["key"]: r["value"] or "" for r in rows}
    finally:
        conn.close()


def set_contact_variable(contact_id: str, key: str, value: Any):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO conversation_variables (contact_id, key, value, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(contact_id, key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
        """, (contact_id, key, str(value), now_iso()))
        conn.commit()
    finally:
        conn.close()


def replace_variables(
    template: str,
    contact: Dict[str, Any],
    message_text: str = "",
    variables: Optional[Dict[str, str]] = None,
    session_name: str = "test"
) -> str:
    if not template:
        return ""

    vars_map = variables.copy() if variables else {}

    # Standard context variables
    context = {
        "contact.name": contact.get("name") or contact.get("push_name") or "Friend",
        "contact.number": contact.get("id") or "",
        "contact.id": contact.get("id") or "",
        "message.text": message_text or "",
        "session": session_name
    }

    # Add conversation variables as {{conversation.var}} and {{var}}
    for k, v in vars_map.items():
        context[f"conversation.{k}"] = str(v)
        if k not in context:
            context[k] = str(v)

    result = template
    for placeholder, val in context.items():
        # Match {{placeholder}} with optional whitespace
        pattern = re.compile(r"\{\{\s*" + re.escape(placeholder) + r"\s*\}\}", re.IGNORECASE)
        result = pattern.sub(str(val), result)

    # Any leftover {{conversation.xyz}} that was unset replaced with empty string
    result = re.sub(r"\{\{\s*conversation\.[a-zA-Z0-9_-]+\s*\}\}", "", result)
    return result


def evaluate_trigger(trigger_type: str, trigger_value: str, incoming_text: str) -> bool:
    if trigger_type == "any":
        return True

    text = (incoming_text or "").strip().lower()
    val = (trigger_value or "").strip().lower()

    if not val and trigger_type != "any":
        return False

    # Comma-separated triggers support
    options = [opt.strip() for opt in val.split(",") if opt.strip()]
    if not options:
        options = [val]

    if trigger_type == "exact":
        return any(text == opt for opt in options)
    elif trigger_type == "contains":
        return any(opt in text for opt in options)
    elif trigger_type == "starts_with":
        return any(text.startswith(opt) for opt in options)
    elif trigger_type == "ends_with":
        return any(text.endswith(opt) for opt in options)
    elif trigger_type == "regex":
        try:
            return bool(re.search(trigger_value, incoming_text, re.IGNORECASE))
        except re.error:
            return False

    return False


def find_matching_flow(incoming_text: str) -> Optional[Dict[str, Any]]:
    conn = get_db()
    try:
        cur = conn.cursor()
        # Fetch enabled flows ordered by priority ASC (lower number = higher priority)
        cur.execute("""
            SELECT * FROM flows
            WHERE enabled = 1
            ORDER BY priority ASC, id ASC
        """)
        flows = [dict(r) for r in cur.fetchall()]

        # 1. Check non-default flows first
        for f in flows:
            if f.get("is_default"):
                continue
            ttype = f.get("trigger_type", "contains")
            tval = f.get("trigger_value", "")
            if evaluate_trigger(ttype, tval, incoming_text):
                return f

        # 2. Check fallback / default flow
        default_flow_id = get_setting("default_flow_id", "")
        if default_flow_id:
            for f in flows:
                if str(f["id"]) == str(default_flow_id):
                    return f

        for f in flows:
            if f.get("is_default"):
                return f

        return None
    finally:
        conn.close()


def find_node(nodes: List[Dict[str, Any]], node_id: str) -> Optional[Dict[str, Any]]:
    for n in nodes:
        if n.get("id") == node_id:
            return n
    return None


def get_outgoing_edges(edges: List[Dict[str, Any]], source_id: str, handle: Optional[str] = None) -> List[Dict[str, Any]]:
    results = []
    for e in edges:
        if e.get("source") == source_id:
            if handle is not None:
                source_handle = e.get("sourceHandle")
                if source_handle == handle:
                    results.append(e)
            else:
                results.append(e)
    return results


def evaluate_condition(
    node_data: Dict[str, Any],
    contact: Dict[str, Any],
    message_text: str,
    variables: Dict[str, str]
) -> bool:
    field = node_data.get("field", "message.text")
    operator = node_data.get("operator", "equals")
    target_value = node_data.get("value", "")

    # Resolve field value
    actual_value = ""
    if field == "message.text":
        actual_value = message_text
    elif field == "contact.number" or field == "contact.id":
        actual_value = contact.get("id", "")
    elif field == "contact.name":
        actual_value = contact.get("name") or contact.get("push_name") or ""
    elif field.startswith("conversation."):
        key = field.split("conversation.", 1)[1]
        actual_value = variables.get(key, "")
    else:
        actual_value = variables.get(field, "")

    actual_str = str(actual_value).strip().lower()
    target_str = str(target_value).strip().lower()

    if operator == "equals":
        return actual_str == target_str
    elif operator == "not_equals":
        return actual_str != target_str
    elif operator == "contains":
        return target_str in actual_str
    elif operator == "not_contains":
        return target_str not in actual_str
    elif operator == "starts_with":
        return actual_str.startswith(target_str)
    elif operator == "ends_with":
        return actual_str.endswith(target_str)
    elif operator == "is_empty":
        return len(actual_str) == 0
    elif operator == "is_not_empty":
        return len(actual_str) > 0
    elif operator == "regex":
        try:
            return bool(re.search(target_value, str(actual_value), re.IGNORECASE))
        except Exception:
            return False

    return False


def match_menu_choice(incoming_text: str, options: List[Dict[str, Any]]) -> Optional[str]:
    text = (incoming_text or "").strip().lower()

    for opt in options:
        opt_id = opt.get("id", "")
        val = str(opt.get("value", "")).strip().lower()
        label = str(opt.get("label", "")).strip().lower()
        pattern = str(opt.get("pattern", "")).strip().lower()

        # 1. Exact or bounded value match (e.g. "1")
        if val and (text == val or re.search(r"(?:^|\s)" + re.escape(val) + r"(?:$|\s)", text)):
            return opt_id

        # 2. Label match (e.g. "Sales", "كول سنتر", "erp")
        if label and (text == label or label in text or text in label):
            return opt_id

        # 3. Custom pattern regex or pipe-separated (e.g. "1|sales|مبيعات")
        if pattern:
            patterns = [p.strip() for p in pattern.split("|") if p.strip()]
            for p in patterns:
                if text == p or p in text or text in p:
                    return opt_id

    return None

async def execute_flow_step(
    flow: Dict[str, Any],
    contact: Dict[str, Any],
    incoming_text: str,
    resume_node_id: Optional[str] = None,
    is_simulation: bool = False
) -> Dict[str, Any]:
    nodes: List[Dict[str, Any]] = json.loads(flow.get("nodes_json") or "[]")
    edges: List[Dict[str, Any]] = json.loads(flow.get("edges_json") or "[]")
    flow_id = flow.get("id")
    contact_id = contact.get("id", "simulator")

    # Trace log for simulator / execution audit
    trace: List[Dict[str, Any]] = []
    variables = get_contact_variables(contact_id) if not is_simulation else contact.get("variables", {}).copy()

    max_steps = int(get_setting("max_execution_steps", "50"))
    step_count = 0

    current_node = None
    next_node_id = None

    # Handle resumption from a paused node (menu or wait_for_reply)
    if resume_node_id:
        current_node = find_node(nodes, resume_node_id)
        if current_node:
            node_type = current_node.get("type")
            node_data = current_node.get("data") or {}

            trace.append({
                "step": step_count,
                "node_id": resume_node_id,
                "type": node_type,
                "title": current_node.get("title", resume_node_id),
                "action": "resumed_from_reply",
                "incoming_text": incoming_text
            })

            log_event(
                direction="system",
                event_type="node_resumed",
                contact_id=contact_id,
                flow_id=flow_id,
                node_id=resume_node_id,
                message_text=f"Resumed on input: {incoming_text}"
            )

            if node_type == "menu":
                options = node_data.get("options") or []
                matched_opt_id = match_menu_choice(incoming_text, options)
                if matched_opt_id:
                    matched_edges = get_outgoing_edges(edges, resume_node_id, handle=matched_opt_id)
                    if not matched_edges:
                        matched_edges = get_outgoing_edges(edges, resume_node_id)
                    next_node_id = matched_edges[0]["target"] if matched_edges else None
                    trace.append({
                        "step": step_count,
                        "action": "menu_choice_matched",
                        "option_id": matched_opt_id,
                        "next_node_id": next_node_id
                    })
                else:
                    # Check otherwise branch
                    fallback_edges = get_outgoing_edges(edges, resume_node_id, handle="otherwise")
                    if fallback_edges:
                        next_node_id = fallback_edges[0]["target"]
                    trace.append({
                        "step": step_count,
                        "action": "menu_choice_otherwise",
                        "next_node_id": next_node_id
                    })

            elif node_type == "wait_for_reply":
                var_name = node_data.get("variable_name")
                if var_name:
                    variables[var_name] = incoming_text
                    if not is_simulation:
                        set_contact_variable(contact_id, var_name, incoming_text)
                    trace.append({
                        "step": step_count,
                        "action": "variable_stored",
                        "variable": var_name,
                        "value": incoming_text
                    })

                out_edges = get_outgoing_edges(edges, resume_node_id)
                next_node_id = out_edges[0]["target"] if out_edges else None

    else:
        # Starting anew: find start node
        for n in nodes:
            if n.get("type") == "start":
                current_node = n
                break
        if not current_node and nodes:
            current_node = nodes[0]

        if current_node:
            trace.append({
                "step": step_count,
                "node_id": current_node.get("id"),
                "type": current_node.get("type"),
                "title": current_node.get("title", "Start"),
                "action": "flow_started"
            })
            out_edges = get_outgoing_edges(edges, current_node.get("id"))
            next_node_id = out_edges[0]["target"] if out_edges else None

    # Main execution loop across nodes
    while next_node_id and step_count < max_steps:
        step_count += 1
        node = find_node(nodes, next_node_id)
        if not node:
            trace.append({"step": step_count, "action": "node_not_found", "node_id": next_node_id})
            break

        node_id = node.get("id")
        node_type = node.get("type")
        node_data = node.get("data") or {}
        node_title = node.get("title", node_type)

        step_info = {
            "step": step_count,
            "node_id": node_id,
            "type": node_type,
            "title": node_title
        }

        # 1. SEND TEXT
        if node_type == "send_text":
            raw_msg = node_data.get("message", "")
            rendered_msg = replace_variables(raw_msg, contact, incoming_text, variables)
            step_info["action"] = "send_text"
            step_info["message"] = rendered_msg

            if not is_simulation:
                try:
                    waha.send_text(contact_id, rendered_msg)
                    log_event(
                        direction="outgoing",
                        event_type="outgoing_message",
                        contact_id=contact_id,
                        flow_id=flow_id,
                        node_id=node_id,
                        message_text=rendered_msg
                    )
                except Exception as e:
                    step_info["error"] = str(e)
                    log_event("error", "send_error", contact_id, flow_id, node_id, str(e))

            out_edges = get_outgoing_edges(edges, node_id)
            next_node_id = out_edges[0]["target"] if out_edges else None

        # 2. CONDITION
        elif node_type == "condition":
            cond_res = evaluate_condition(node_data, contact, incoming_text, variables)
            handle = "yes" if cond_res else "no"
            step_info["action"] = "condition_evaluated"
            step_info["result"] = cond_res
            step_info["branch"] = handle

            log_event(
                direction="system",
                event_type="condition_result",
                contact_id=contact_id,
                flow_id=flow_id,
                node_id=node_id,
                message_text=f"Condition {node_data.get('field')} {node_data.get('operator')} -> {cond_res}"
            )

            branch_edges = get_outgoing_edges(edges, node_id, handle=handle)
            next_node_id = branch_edges[0]["target"] if branch_edges else None

        # 3. MENU / CHOICE
        elif node_type == "menu":
            menu_msg = (node_data.get("message") or "").strip()
            options = node_data.get("options") or []
            rendered_msg = replace_variables(menu_msg, contact, incoming_text, variables)

            # Ensure options are formatted and presented clearly to the customer
            if options:
                all_in_msg = all(opt.get("label", "").strip() in rendered_msg for opt in options if opt.get("label", "").strip())
                if not all_in_msg:
                    formatted_opts = []
                    for i, opt in enumerate(options):
                        val = str(opt.get("value") or (i + 1)).strip()
                        lbl = str(opt.get("label") or opt.get("value") or f"Option {i+1}").strip()
                        formatted_opts.append(f"*{val}* - {lbl}")
                    options_block = "\n".join(formatted_opts)
                    if rendered_msg:
                        rendered_msg = f"{rendered_msg}\n\n{options_block}"
                    else:
                        rendered_msg = f"Please choose:\n\n{options_block}"

            step_info["action"] = "menu_prompt_sent"
            step_info["message"] = rendered_msg
            step_info["options"] = options

            if not is_simulation:
                try:
                    waha.send_text(contact_id, rendered_msg)
                    log_event(
                        direction="outgoing",
                        event_type="outgoing_message",
                        contact_id=contact_id,
                        flow_id=flow_id,
                        node_id=node_id,
                        message_text=rendered_msg
                    )
                except Exception as e:
                    step_info["error"] = str(e)
            # Pause flow here and wait for customer to pick a choice
            step_info["status"] = "waiting_for_reply"
            trace.append(step_info)

            if not is_simulation:
                update_conversation_state(contact_id, flow_id, node_id, status="waiting_for_reply")

            return {
                "status": "waiting_for_reply",
                "current_node_id": node_id,
                "trace": trace,
                "variables": variables
            }

        # 4. WAIT FOR REPLY
        elif node_type == "wait_for_reply":
            prompt = node_data.get("prompt_message")
            if prompt:
                rendered_prompt = replace_variables(prompt, contact, incoming_text, variables)
                step_info["action"] = "wait_prompt_sent"
                step_info["message"] = rendered_prompt
                if not is_simulation:
                    try:
                        waha.send_text(contact_id, rendered_prompt)
                        log_event("outgoing", "outgoing_message", contact_id, flow_id, node_id, rendered_prompt)
                    except Exception as e:
                        step_info["error"] = str(e)

            step_info["status"] = "waiting_for_reply"
            step_info["variable_name"] = node_data.get("variable_name")
            trace.append(step_info)

            if not is_simulation:
                update_conversation_state(contact_id, flow_id, node_id, status="waiting_for_reply")

            return {
                "status": "waiting_for_reply",
                "current_node_id": node_id,
                "trace": trace,
                "variables": variables
            }

        # 5. SET VARIABLE
        elif node_type == "set_variable":
            var_name = node_data.get("variable_name")
            raw_val = node_data.get("variable_value", "")
            rendered_val = replace_variables(raw_val, contact, incoming_text, variables)

            if var_name:
                variables[var_name] = rendered_val
                if not is_simulation:
                    set_contact_variable(contact_id, var_name, rendered_val)
                step_info["action"] = "set_variable"
                step_info["variable"] = var_name
                step_info["value"] = rendered_val
                log_event("system", "variable_set", contact_id, flow_id, node_id, f"{var_name} = {rendered_val}")

            out_edges = get_outgoing_edges(edges, node_id)
            next_node_id = out_edges[0]["target"] if out_edges else None

        # 6. SEND IMAGE
        elif node_type == "send_image":
            img_url = replace_variables(node_data.get("image_url", ""), contact, incoming_text, variables)
            caption = replace_variables(node_data.get("caption", ""), contact, incoming_text, variables)
            step_info["action"] = "send_image"
            step_info["image_url"] = img_url
            step_info["caption"] = caption

            if not is_simulation:
                try:
                    waha.send_image(contact_id, img_url, caption=caption or None)
                    log_event("outgoing", "outgoing_image", contact_id, flow_id, node_id, f"Image: {img_url}")
                except Exception as e:
                    step_info["error"] = str(e)
                    log_event("error", "send_image_error", contact_id, flow_id, node_id, str(e))

            out_edges = get_outgoing_edges(edges, node_id)
            next_node_id = out_edges[0]["target"] if out_edges else None

        # 7. SEND FILE
        elif node_type == "send_file":
            file_url = replace_variables(node_data.get("file_url", ""), contact, incoming_text, variables)
            filename = replace_variables(node_data.get("filename", ""), contact, incoming_text, variables)
            caption = replace_variables(node_data.get("caption", ""), contact, incoming_text, variables)
            step_info["action"] = "send_file"
            step_info["file_url"] = file_url

            if not is_simulation:
                try:
                    waha.send_file(contact_id, file_url, filename=filename or None, caption=caption or None)
                    log_event("outgoing", "outgoing_file", contact_id, flow_id, node_id, f"File: {file_url}")
                except Exception as e:
                    step_info["error"] = str(e)
                    log_event("error", "send_file_error", contact_id, flow_id, node_id, str(e))

            out_edges = get_outgoing_edges(edges, node_id)
            next_node_id = out_edges[0]["target"] if out_edges else None

        # 8. DELAY
        elif node_type == "delay":
            secs = min(max(int(node_data.get("seconds", 2)), 1), 10)
            step_info["action"] = "delay"
            step_info["seconds"] = secs

            if not is_simulation:
                await asyncio.sleep(secs)
                log_event("system", "delay_completed", contact_id, flow_id, node_id, f"Waited {secs}s")

            out_edges = get_outgoing_edges(edges, node_id)
            next_node_id = out_edges[0]["target"] if out_edges else None

        # 9. HTTP REQUEST
        elif node_type == "http_request":
            method = (node_data.get("method") or "POST").upper()
            url = replace_variables(node_data.get("url", ""), contact, incoming_text, variables)
            resp_var = node_data.get("response_variable")

            # Parse headers and body
            headers = {"Content-Type": "application/json"}
            raw_headers = node_data.get("headers")
            if raw_headers:
                try:
                    headers.update(json.loads(replace_variables(raw_headers, contact, incoming_text, variables)))
                except Exception:
                    pass

            body_str = replace_variables(node_data.get("body", ""), contact, incoming_text, variables)
            json_payload = None
            if body_str:
                try:
                    json_payload = json.loads(body_str)
                except Exception:
                    pass

            step_info["action"] = "http_request"
            step_info["method"] = method
            step_info["url"] = url

            if not is_simulation and url:
                try:
                    res = requests.request(
                        method=method,
                        url=url,
                        headers=headers,
                        json=json_payload if json_payload is not None else None,
                        data=body_str if json_payload is None else None,
                        timeout=15
                    )
                    res_text = res.text
                    step_info["http_status"] = res.status_code
                    if resp_var:
                        variables[resp_var] = res_text
                        set_contact_variable(contact_id, resp_var, res_text)
                    log_event("system", "http_request", contact_id, flow_id, node_id, f"{method} {url} -> {res.status_code}")
                except Exception as e:
                    step_info["http_error"] = str(e)
                    log_event("error", "http_error", contact_id, flow_id, node_id, str(e))

            out_edges = get_outgoing_edges(edges, node_id)
            next_node_id = out_edges[0]["target"] if out_edges else None

        # 10. HUMAN HANDOFF
        elif node_type == "human_handoff":
            notify_msg = node_data.get("notify_message")
            if notify_msg:
                rendered_notify = replace_variables(notify_msg, contact, incoming_text, variables)
                if not is_simulation:
                    try:
                        waha.send_text(contact_id, rendered_notify)
                        log_event("outgoing", "outgoing_message", contact_id, flow_id, node_id, rendered_notify)
                    except Exception:
                        pass

            step_info["action"] = "human_handoff"
            trace.append(step_info)

            if not is_simulation:
                update_conversation_state(contact_id, flow_id, node_id, status="human_mode")
                conn = get_db()
                try:
                    conn.execute("UPDATE contacts SET bot_disabled = 1 WHERE id = ?", (contact_id,))
                    conn.commit()
                finally:
                    conn.close()
                log_event("system", "human_handoff", contact_id, flow_id, node_id, "Automated bot paused for agent")

            return {
                "status": "human_mode",
                "current_node_id": node_id,
                "trace": trace,
                "variables": variables
            }

        # 11. END FLOW
        elif node_type == "end":
            step_info["action"] = "end_flow"
            trace.append(step_info)

            if not is_simulation:
                update_conversation_state(contact_id, flow_id, node_id, status="completed")
                log_event("system", "flow_ended", contact_id, flow_id, node_id, "Flow completed")

            return {
                "status": "completed",
                "current_node_id": node_id,
                "trace": trace,
                "variables": variables
            }

        trace.append(step_info)

    # Reached end of connected path
    if not is_simulation:
        update_conversation_state(contact_id, flow_id, next_node_id, status="completed")

    return {
        "status": "completed",
        "current_node_id": next_node_id,
        "trace": trace,
        "variables": variables
    }


def update_conversation_state(
    contact_id: str,
    flow_id: Optional[int],
    current_node_id: Optional[str],
    status: str = "active"
):
    conn = get_db()
    try:
        now = now_iso()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO conversations (contact_id, flow_id, current_node_id, status, last_message_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(contact_id) DO UPDATE SET
                flow_id = excluded.flow_id,
                current_node_id = excluded.current_node_id,
                status = excluded.status,
                last_message_at = excluded.last_message_at,
                updated_at = excluded.updated_at
        """, (contact_id, flow_id, current_node_id, status, now, now))
        conn.commit()
    finally:
        conn.close()


def get_conversation_state(contact_id: str) -> Optional[Dict[str, Any]]:
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM conversations WHERE contact_id = ?", (contact_id,))
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


async def process_incoming_message(
    contact_id: str,
    message_text: str,
    sender_name: str = "",
    push_name: str = "",
    lid: str = ""
) -> Dict[str, Any]:
    # 1. Check Global Bot Status
    bot_enabled = get_setting("bot_enabled", "true").lower() == "true"

    # Always log incoming message
    log_event(
        direction="incoming",
        event_type="incoming_message",
        contact_id=contact_id,
        message_text=message_text,
        details={"sender_name": sender_name, "push_name": push_name, "lid": lid}
    )

    # Upsert contact record
    conn = get_db()
    contact = None
    try:
        cur = conn.cursor()
        now = now_iso()
        cur.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,))
        existing = cur.fetchone()
        if existing:
            contact = dict(existing)
            # Update last_seen and any new name/lid
            cur.execute("""
                UPDATE contacts SET
                    name = COALESCE(?, name),
                    push_name = COALESCE(?, push_name),
                    lid = COALESCE(?, lid),
                    last_seen = ?
                WHERE id = ?
            """, (sender_name or None, push_name or None, lid or None, now, contact_id))
        else:
            cur.execute("""
                INSERT INTO contacts (id, name, push_name, lid, bot_disabled, last_seen)
                VALUES (?, ?, ?, ?, 0, ?)
            """, (contact_id, sender_name or push_name or "Friend", push_name, lid, now))
            contact = {
                "id": contact_id,
                "name": sender_name or push_name or "Friend",
                "push_name": push_name,
                "lid": lid,
                "bot_disabled": 0
            }
        conn.commit()
    finally:
        conn.close()

    if not bot_enabled:
        return {"status": "ignored", "reason": "bot_globally_disabled"}

    # 2. Check Contact-specific Bot Disable (Human Agent Takeover)
    if contact.get("bot_disabled"):
        return {"status": "ignored", "reason": "contact_bot_disabled"}

    # 3. Check Conversation State: is contact currently waiting for reply inside an active flow?
    conv = get_conversation_state(contact_id)
    if conv and conv.get("status") == "human_mode":
        return {"status": "ignored", "reason": "in_human_mode"}

    if conv and conv.get("status") == "waiting_for_reply" and conv.get("flow_id") and conv.get("current_node_id"):
        # Resume active flow from current waiting node!
        conn = get_db()
        flow = None
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM flows WHERE id = ?", (conv["flow_id"],))
            frow = cur.fetchone()
            if frow:
                flow = dict(frow)
        finally:
            conn.close()

        if flow and flow.get("enabled"):
            return await execute_flow_step(
                flow=flow,
                contact=contact,
                incoming_text=message_text,
                resume_node_id=conv["current_node_id"],
                is_simulation=False
            )

    # 4. Otherwise, evaluate flow triggers by priority
    matched_flow = find_matching_flow(message_text)
    if not matched_flow:
        log_event("system", "no_flow_matched", contact_id, None, None, f"No trigger for: {message_text}")
        return {"status": "no_match"}

    log_event(
        direction="system",
        event_type="flow_matched",
        contact_id=contact_id,
        flow_id=matched_flow["id"],
        message_text=f"Matched flow '{matched_flow['name']}' on: {message_text}"
    )

    return await execute_flow_step(
        flow=matched_flow,
        contact=contact,
        incoming_text=message_text,
        resume_node_id=None,
        is_simulation=False
    )
