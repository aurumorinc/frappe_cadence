import frappe
import requests
import json
import urllib.parse
import hmac
import hashlib
from frappe_campaign.email_campaign import get as get_campaign_payload

def queue_generation_task(campaign_name, schedule_idx):
    """
    Constructs the rich payload, generates the callbacks, and creates the Integration Request.
    """
    filters = [["Campaign Email Schedule", "idx", "=", schedule_idx]]
    fields = ["*"]
    
    agent_payload = get_campaign_payload(name=campaign_name, filters=filters, fields=fields)
    
    # Generate Callback URL
    base_callback_url = frappe.utils.get_url("/api/method/frappe_campaign.email_campaign.update")
    query_params = urllib.parse.urlencode({
        "filters": json.dumps([["Email Campaign", "name", "=", campaign_name]])
    })
    callback_url = f"{base_callback_url}?{query_params}"
    
    agent_payload["callback"] = {
        "url": callback_url,
        "method": "POST",
        "headers": {}
    }
    
    # Create the Integration Request
    integration_request = frappe.get_doc({
        "doctype": "Integration Request",
        "integration_request_service": "AI Agent",
        "request_description": f"Generate Prompt for {campaign_name} - Step {schedule_idx}",
        "reference_doctype": "Email Campaign",
        "reference_docname": campaign_name,
        "status": "Queued",
        "data": "{}" # placeholder
    })
    integration_request.insert(ignore_permissions=True)
    
    # Inject the generated ID into the payload and update the document data
    agent_payload["integration_request_id"] = integration_request.name
    integration_request.db_set("data", frappe.as_json(agent_payload))
    
    # Enqueue the "dumb" dispatcher
    frappe.enqueue("frappe_campaign.utils.agent.dispatch_integration_request", integration_request_name=integration_request.name)

def dispatch_integration_request(integration_request_name):
    """
    A simple dispatcher that merely reads the Integration Request data and fires the POST request.
    """
    doc = frappe.get_doc("Integration Request", integration_request_name)
    if doc.status != "Queued":
        return

    agent_payload = json.loads(doc.data)
    
    campaign_agent_base_url = frappe.conf.get("campaign_agent_base_url") 
    campaign_agent_api_key = frappe.conf.get("campaign_agent_api_key")
    campaign_agent_webhook_secret = frappe.conf.get("campaign_agent_webhook_secret")
    
    if not campaign_agent_base_url:
        error_msg = "Agent Base URL missing in site_config.json"
        frappe.log_error(error_msg, "Agent Webhook Error")
        doc.db_set("status", "Failed")
        doc.db_set("error", error_msg)
        return
        
    headers = {
        "Content-Type": "application/json"
    }
    
    if campaign_agent_api_key:
        headers["Authorization"] = f"Bearer {campaign_agent_api_key}"
    
    payload_json = json.dumps(agent_payload, separators=(',', ':'))
    
    if campaign_agent_webhook_secret:
        import base64
        signature = base64.b64encode(
            hmac.new(
                campaign_agent_webhook_secret.encode("utf8"),
                payload_json.encode("utf8"),
                hashlib.sha256,
            ).digest()
        )
        headers["X-Frappe-Webhook-Signature"] = signature
    
    try:
        response = requests.post(campaign_agent_base_url, headers=headers, data=payload_json, timeout=10)
        response.raise_for_status()
        doc.db_set("status", "Authorized") # Mark as successfully dispatched
    except Exception as e:
        error_log = f"Failed to send task to Agent: {str(e)}\n{response.text if 'response' in locals() else ''}"
        frappe.log_error(error_log, "Agent Error")
        doc.db_set("status", "Failed")
        doc.db_set("error", error_log)
