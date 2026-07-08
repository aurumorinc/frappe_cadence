import frappe
import requests
from typing import Dict, Any

def get_sift_settings() -> tuple:
    settings = frappe.get_single("Sift Settings")
    if not settings.sift_base_url or not settings.sift_api_key:
        frappe.throw("Sift Base URL and API Key must be configured in Sift Settings.")
    return settings.sift_base_url.rstrip('/'), settings.get_password('sift_api_key')

def get_history(reference_doctype: str, reference_name: str) -> list:
    histories = frappe.get_all(
        "History",
        filters={"reference_doctype": reference_doctype, "reference_name": reference_name},
        fields=["name", "content"],
        order_by="creation asc"
    )
    
    messages = []
    for h in histories:
        content_blocks = []
        if h.content:
            content_blocks.append({"type": "text", "text": h.content})
            
        history_images = frappe.get_all(
            "History Image",
            filters={"parent": h.name, "parenttype": "History"},
            fields=["image"]
        )
        
        for img in history_images:
            if img.image:
                try:
                    file_doc = frappe.get_doc("File", {"file_url": img.image})
                    content_blocks.append({
                        "type": "image_url",
                        "image_url": {"url": file_doc.presigned_url}
                    })
                except frappe.DoesNotExistError:
                    pass

        if content_blocks:
            messages.append({"role": "user", "content": content_blocks})
            
    return messages

@frappe.whitelist()
def optimize(template_doctype: str, template_name: str) -> None:
    template = frappe.get_doc(template_doctype, template_name)
    
    template.db_set("status", "Optimizing")
    
    base_url, api_key = get_sift_settings()
    
    annotations = template.get("annotations", [])
    train_data = []
    
    for ann in annotations:
        if ann.input and ann.output:
            messages = [{"role": "system", "content": template.system_prompt}]
            
            history_messages = get_history(ann.reference_doctype, ann.reference_name)
            messages.extend(history_messages)
            
            messages.append({"role": "user", "content": [{"type": "text", "text": ann.input}]})
            
            train_data.append({
                "trace_id": ann.name,
                "score": 1.0,
                "messages": messages,
                "feedback": ann.output
            })
            
    payload = {
        "agent_name": f"agent-{template_name}",
        "webhook_url": f"{frappe.utils.get_url()}/api/method/frappe_cadence.utils.sift.optimize_callback",
        "metadata": {
            "template_doctype": template_doctype,
            "template_name": template_name
        },
        "litellm_params": {
            "model": "openai/gpt-4o"
        },
        "dspy_params": {
            "state": {
                "default": {
                    "train": train_data
                }
            }
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
            
            messages = [{"role": "system", "content": template.system_prompt}]
            history_messages = get_history(ann.reference_doctype, ann.reference_name)
            messages.extend(history_messages)
            messages.append({"role": "user", "content": [{"type": "text", "text": ann.input}]})
            
            payload = {
                "model": template.sift_id,
                "webhook_url": webhook_url,
                "metadata": {
                    "annotation_id": ann.name
                },
                "input": messages
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
