import frappe
import requests
import json
import urllib.parse
import hmac
import hashlib
import base64
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
    
    template_doctype = f"{schedule.reference_doctype}"
    template_name = schedule.reference_name
    template = frappe.get_doc(template_doctype, template_name)
    
    channel = template_doctype.replace(" Template", "")

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
            "delivery_status": "Scheduled"
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
                "status": "Open"
            })
            comm.insert(ignore_permissions=True)
            comm_name = comm.name
            
            # Construct AI Agent payload
            cadence = frappe.get_doc("Multi Channel Cadence", cadence_name)
            lead = frappe.get_doc(cadence.cadence_for, cadence.recipient)
            
            # Fetch History records
            from frappe.utils import add_months, today, get_url
            three_months_ago = add_months(today(), -3)
            
            # Get history for lead
            history_filters = [
                ["creation", ">=", three_months_ago],
                ["reference_doctype", "=", cadence.cadence_for],
                ["reference_name", "=", lead.name]
            ]
            histories = frappe.get_all("History", filters=history_filters, fields=["*"])
            
            # Get history for organization if it's a CRM Lead
            if cadence.cadence_for == "CRM Lead" and lead.organization:
                org_histories = frappe.get_all("History", filters=[
                    ["creation", ">=", three_months_ago],
                    ["reference_doctype", "=", "CRM Organization"],
                    ["reference_name", "=", lead.organization]
                ], fields=["*"])
                histories.extend(org_histories)
            
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
                "input": [
                    {
                        "role": "system",
                        "content": [{"type": "input_text", "text": template.system_prompt}]
                    },
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": template.user_prompt}
                        ]
                    }
                ]
            }
            
            for history in histories:
                if history.image:
                    payload["input"][1]["content"].append({
                        "type": "input_image",
                        "image_url": get_url(history.image)
                    })
            
            cache_val = frappe.cache().get_value(f"ai_req:{cadence_name}:{schedule_name}")
            
            if not cache_val:
                # Send POST request to AI Agent webhook
                cadence_agent_base_url = frappe.conf.get("cadence_agent_base_url")
                cadence_agent_api_key = frappe.conf.get("cadence_agent_api_key")
                cadence_agent_webhook_secret = frappe.conf.get("cadence_agent_webhook_secret")
                
                if cadence_agent_base_url:
                    headers = {"Content-Type": "application/json"}
                    if cadence_agent_api_key:
                        headers["Authorization"] = f"Bearer {cadence_agent_api_key}"
                    
                    payload_json = json.dumps(payload, separators=(',', ':'))
                    
                    if cadence_agent_webhook_secret:
                        signature = base64.b64encode(
                            hmac.new(
                                cadence_agent_webhook_secret.encode("utf8"),
                                payload_json.encode("utf8"),
                                hashlib.sha256,
                            ).digest()
                        ).decode("utf8")
                        headers["X-Frappe-Webhook-Signature"] = signature
                    
                    try:
                        requests.post(cadence_agent_base_url, headers=headers, data=payload_json, timeout=10)
                        frappe.cache().set_value(f"ai_req:{cadence_name}:{schedule_name}", 1, expires_in_sec=86400)
                    except Exception as e:
                        frappe.log_error(f"Failed to send task to Agent: {str(e)}", "Agent Error")
        else:
            comm_name = draft_comm[0].name
            
        wait_for_event("ai_agent_callback", condition=f"argument.get('communication_id') == '{comm_name}'")

@frappe.whitelist(allow_guest=True)
def callback():
    """
    Webhook endpoint for AI callbacks.
    """
    try:
        payload = frappe.request.json
        communication_id = payload.get("metadata", {}).get("name")
        
        if not communication_id:
            return {"status": "error", "message": "Missing communication_id in metadata"}
            
        output_text = payload.get("output", [{}])[0].get("content", [{}])[0].get("text")
        if not output_text:
            return {"status": "error", "message": "Missing output text"}
            
        parsed_json = json.loads(output_text)
        
        comm = frappe.get_doc("Communication", communication_id)
        if parsed_json.get("subject"):
            comm.subject = parsed_json.get("subject")
        else:
            comm.subject = f"{comm.communication_medium} Message"
        comm.content = parsed_json.get("content")
        comm.delivery_status = "Scheduled"
        comm.save(ignore_permissions=True)
        
        emit_event("ai_agent_callback", {"communication_id": communication_id})
        
        return {"status": "success"}
    except Exception as e:
        frappe.log_error(f"AI Agent Callback Error: {str(e)}", "Agent Error")
        return {"status": "error", "message": str(e)}
