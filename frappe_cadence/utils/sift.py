import frappe
import requests
from typing import Dict, Any

def get_sift_settings() -> tuple:
    settings = frappe.get_single("Sift Settings")
    if not settings.sift_base_url or not settings.sift_api_key:
        frappe.throw("Sift Base URL and API Key must be configured in Sift Settings.")
    return settings.sift_base_url.rstrip('/'), settings.get_password('sift_api_key')

def get_history_content(reference_doctype: str, reference_name: str) -> str:
    histories = frappe.get_all(
        "History",
        filters={"reference_doctype": reference_doctype, "reference_name": reference_name},
        fields=["content"],
        order_by="creation asc"
    )
    return "\n\n".join([h.content for h in histories if h.content])

@frappe.whitelist()
def optimize(template_doctype: str, template_name: str) -> None:
    template = frappe.get_doc(template_doctype, template_name)
    
    template.db_set("status", "Optimizing")
    
    base_url, api_key = get_sift_settings()
    
    annotations = template.get("annotations", [])
    few_shot_examples = []
    
    for ann in annotations:
        if ann.input and ann.output:
            history_context = get_history_content(ann.reference_doctype, ann.reference_name)
            example = {
                "input": ann.input,
                "output": ann.output,
                "history": history_context
            }
            few_shot_examples.append(example)
            
    payload = {
        "system_prompt": template.system_prompt,
        "user_prompt": template.user_prompt,
        "few_shot_examples": few_shot_examples,
        "webhook_url": f"{frappe.utils.get_url()}/api/method/frappe_cadence.utils.sift.optimize_callback",
        "metadata": {
            "template_doctype": template_doctype,
            "template_name": template_name
        }
    }
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(f"{base_url}/agents", json=payload, headers=headers, timeout=10)
        response.raise_for_status()
    except Exception as e:
        template.db_set("status", "Enabled")
        frappe.throw(f"Failed to initiate optimization with Sift: {str(e)}")

@frappe.whitelist(allow_guest=True)
def optimize_callback(**kwargs) -> Dict[str, str]:
    # Extract data from webhook payload
    # Assuming standard JSON payload mapped to kwargs
    metadata = kwargs.get("metadata", {})
    if isinstance(metadata, str):
        import json
        try:
            metadata = json.loads(metadata)
        except Exception:
            metadata = {}
            
    template_doctype = metadata.get("template_doctype")
    template_name = metadata.get("template_name")
    agent_name = kwargs.get("agent_name")
    
    if not template_doctype or not template_name or not agent_name:
        frappe.throw("Invalid webhook payload")
        
    template = frappe.get_doc(template_doctype, template_name)
    template.db_set("sift_id", agent_name)
    template.db_set("status", "Disabled")
    
    return {"status": "success"}

@frappe.whitelist()
def predict(template_doctype: str, template_name: str) -> None:
    template = frappe.get_doc(template_doctype, template_name)
    
    if not template.sift_id:
        frappe.throw("Template must be optimized first (missing sift_id)")
        
    template.db_set("status", "Predicting")
    
    base_url, api_key = get_sift_settings()
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    annotations = template.get("annotations", [])
    webhook_url = f"{frappe.utils.get_url()}/api/method/frappe_cadence.utils.sift.predict_callback"
    
    has_pending = False
    
    for ann in annotations:
        if not ann.output:
            has_pending = True
            history_context = get_history_content(ann.reference_doctype, ann.reference_name)
            
            payload = {
                "agent_name": template.sift_id,
                "input": ann.input,
                "history": history_context,
                "webhook_url": webhook_url,
                "metadata": {
                    "annotation_id": ann.name
                }
            }
            
            try:
                requests.post(f"{base_url}/responses", json=payload, headers=headers, timeout=10)
            except Exception as e:
                frappe.log_error(f"Sift Predict Error for annotation {ann.name}: {str(e)}", "Sift API")
                
    if not has_pending:
        template.db_set("status", "Disabled")
        frappe.msgprint("No pending annotations without output found.")

@frappe.whitelist(allow_guest=True)
def predict_callback(**kwargs) -> Dict[str, str]:
    metadata = kwargs.get("metadata", {})
    if isinstance(metadata, str):
        import json
        try:
            metadata = json.loads(metadata)
        except Exception:
            metadata = {}
            
    annotation_id = metadata.get("annotation_id")
    output_text = kwargs.get("output_text", kwargs.get("response", "")) # support different response keys
    
    if not annotation_id or not output_text:
        frappe.throw("Invalid webhook payload")
        
    frappe.db.set_value("Annotation", annotation_id, "output", output_text)
    
    return {"status": "success"}
