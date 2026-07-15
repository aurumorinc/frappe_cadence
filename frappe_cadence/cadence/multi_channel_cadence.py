import frappe
import requests
import json
import urllib.parse
import hmac
import hashlib
import base64
from frappe.utils import add_months, today, get_url
from frappe_controller.utils.controller import wait_for_event, emit_event

def process_cadence_step(cadence_name, schedule_name, previous_schedule_name=None):
    """
    Processes a single step in a multi-channel cadence.
    Must be idempotent as it executes from line 1 when resumed.
    """
    # 1. Wait for Previous Step
    if previous_schedule_name:
        prev_comm = frappe.get_all("Communication", filters={
            "reference_doctype": "Multi Channel Cadence",
            "reference_name": cadence_name,
            "cadence_schedule": previous_schedule_name,
            "delivery_status": ["in", ["Scheduled", "Sent"]]
        })
        if not prev_comm:
            wait_for_event(
                "cadence_step_completed",
                condition=f"argument.get('cadence_name') == '{cadence_name}' and argument.get('schedule_name') == '{previous_schedule_name}'"
            )
            return

    # 2. Idempotency Check
    curr_comm = frappe.get_all("Communication", filters={
        "reference_doctype": "Multi Channel Cadence",
        "reference_name": cadence_name,
        "cadence_schedule": schedule_name,
        "delivery_status": ["in", ["Scheduled", "Sent"]]
    })
    if curr_comm:
        emit_event("cadence_step_completed", {"cadence_name": cadence_name, "schedule_name": schedule_name})
        return

    # 3. Process Template
    schedule = frappe.get_doc("Cadence Multi Channel Schedule", schedule_name)
    mcc = frappe.get_doc("Multi Channel Cadence", cadence_name)
    
    template_doctype = f"{schedule.reference_doctype}"
    template_name = schedule.reference_name
    template = frappe.get_doc(template_doctype, template_name)
    
    channel = template_doctype.replace(" Template", "")

    reference_cadence_provider = None
    for row in (mcc.get("provider") or []):
        if row.channel == channel:
            reference_cadence_provider = row.cadence_provider
            break

    if template.status == "Enabled":
        comm = frappe.get_doc({
            "doctype": "Communication",
            "communication_medium": channel,
            "subject": getattr(template, "subject", template.get("title", f"{channel} Message")),
            "content": template.get("message") or template.get("response"),
            "reference_doctype": "Multi Channel Cadence",
            "reference_name": cadence_name,
            "cadence_schedule": schedule_name,
            "status": "Open",
            "delivery_status": "Scheduled",
            "reference_cadence_provider": reference_cadence_provider
        })
        comm.insert(ignore_permissions=True)
        emit_event("cadence_step_completed", {"cadence_name": cadence_name, "schedule_name": schedule_name})
        return

    if template.status == "Prompt":
        draft_comm = frappe.get_all("Communication", filters={
            "reference_doctype": "Multi Channel Cadence",
            "reference_name": cadence_name,
            "cadence_schedule": schedule_name,
            "status": "Open"
        })
        
        if not draft_comm:
            comm = frappe.get_doc({
                "doctype": "Communication",
                "communication_medium": channel,
                "subject": f"Draft {channel} Message",
                "reference_doctype": "Multi Channel Cadence",
                "reference_name": cadence_name,
                "cadence_schedule": schedule_name,
                "status": "Open",
                "reference_cadence_provider": reference_cadence_provider
            })
            comm.insert(ignore_permissions=True)
            comm_name = comm.name
            
            # Construct AI Agent payload
            cadence = frappe.get_doc("Multi Channel Cadence", cadence_name)
            lead = frappe.get_doc(cadence.cadence_for, cadence.recipient)
            
            schema_properties = {
                "content": {
                    "type": "string",
                    "description": "The main body content of the message"
                }
            }
            required_fields = ["content"]
            
            if channel == "Email":
                schema_properties["subject"] = {
                    "type": "string",
                    "description": "The subject of the message"
                }
                required_fields.append("subject")
                
            payload = {
                "metadata": {
                    "name": comm_name
                },
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "communication_generation",
                        "strict": True,
                        "schema": {
                            "type": "object",
                            "properties": schema_properties,
                            "required": required_fields,
                            "additionalProperties": False
                        }
                    }
                },
            }
            
            from markdownify import markdownify
            from frappe_cadence.cadence.doctype.history.history import get_history
            from frappe_cadence.cadence.doctype.user_bio.user_bio import get_user_bio
            
            sender_bio_content = get_user_bio(mcc.owner, cadence_name)
            if not sender_bio_content:
                wait_for_event("user_bio_created", condition=f"argument.get('reference_user') == '{mcc.owner}'")
                return
                
            sender = frappe.db.get_value("User", mcc.owner, ["full_name"], as_dict=True) or {}
            sender_name = sender.get("full_name") or ""
            sender_bio = markdownify(sender_bio_content)
            
            payload["input"] = []
            if sender_name or sender_bio:
                payload["input"].append({
                    "role": "system",
                    "content": f"Sender Name: {sender_name}\nSender Bio:\n{sender_bio}"
                })
            
            # Fetch and format History records
            three_months_ago = add_months(today(), -3)
            history_messages = get_history(cadence.cadence_for, cadence.recipient, since_date=three_months_ago)
            payload["input"].extend(history_messages)

            # Use /responses endpoint instead of /agents and map cadence model
            payload["model"] = cadence.sift_id or "default-model"
            
            cache_val = frappe.cache().get_value(f"ai_req:{cadence_name}:{schedule_name}")
            
            if not cache_val:
                sift_settings = frappe.get_single("Sift Settings")
                sift_base_url = sift_settings.sift_base_url
                sift_api_key = sift_settings.get_password("sift_api_key")
                
                if sift_base_url:
                    headers = {"Content-Type": "application/json"}
                    if sift_api_key:
                        headers["Authorization"] = f"Bearer {sift_api_key}"
                    
                    # Add webhook info to payload so Sift knows where to callback
                    webhook_url = get_url(f"/api/method/frappe_cadence.cadence.{channel.lower()}_template.callback")
                    payload["background"] = True
                    payload["webhook"] = {
                        "url": webhook_url,
                        "events": ["completed", "failed"]
                    }

                    payload_json = json.dumps(payload, separators=(',', ':'))
                    
                    try:
                        requests.post(f"{sift_base_url}/responses", headers=headers, data=payload_json, timeout=10)
                        frappe.cache().set_value(f"ai_req:{cadence_name}:{schedule_name}", 1, expires_in_sec=86400)
                    except Exception as e:
                        frappe.log_error(title="Agent Error", message=f"Failed to send task to Agent: {str(e)}")
                        return
                else:
                    frappe.log_error(title="Sift Configuration Error", message="Sift Base URL not configured.")
                    return
        else:
            comm_name = draft_comm[0].name
            
        wait_for_event("callback", condition=f"argument.get('communication_id') == '{comm_name}'")
