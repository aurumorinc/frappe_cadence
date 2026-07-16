import frappe
import json
from frappe_controller.utils.controller import emit_event

@frappe.whitelist(allow_guest=True)
def callback():
    """
    Webhook endpoint for Sift callbacks for SMS Template.
    """
    try:
        payload = frappe.request.json
        event_type = payload.get("type")
        
        if event_type and event_type.endswith(".started"):
            return {"status": "ignored"}
            
        if event_type and event_type.endswith(".failed"):
            frappe.log_error(title="Sift Callback Failed", message=payload.get("error") or "Unknown error")
            return {"status": "failed"}
            
        communication_id = payload.get("metadata", {}).get("name")
        if not communication_id:
            return {"status": "error", "message": "Missing communication_id in metadata"}
            
        data = payload.get("data", [])
        output_text = ""
        if isinstance(data, list) and len(data) > 0:
            content_list = data[0].get("content", [])
            if content_list and isinstance(content_list, list) and len(content_list) > 0:
                output_text = content_list[0].get("text", "")
                
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
        
        emit_event("callback", {"communication_id": communication_id})
        
        return {"status": "success"}
    except Exception as e:
        frappe.log_error(title="Sift Callback Error", message=str(e))
        return {"status": "error", "message": str(e)}
