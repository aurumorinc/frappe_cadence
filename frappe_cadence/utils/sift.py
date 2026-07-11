import frappe
import requests
from typing import Dict, Any, Union

def get_sift_settings() -> tuple:
    settings = frappe.get_single("Sift Settings")
    base_url = settings.sift_base_url or frappe.conf.get("sift_base_url")
    api_key = settings.get_password('sift_api_key') or frappe.conf.get("sift_api_key")
    
    if not base_url or not api_key:
        frappe.throw("Sift Base URL and API Key must be configured in Sift Settings or site config.")
        
    return base_url.rstrip('/'), api_key

def get_history(reference_doctype: str, reference_name: str) -> list:
    histories = frappe.get_all(
        "History",
        filters={"reference_doctype": reference_doctype, "reference_name": reference_name},
        fields=["name", "content"],
        order_by="creation asc"
    )
    
    messages = []
    from markdownify import markdownify
    for h in histories:
        content_blocks = []
        if h.content:
            content_blocks.append({"type": "text", "text": markdownify(h.content)})
            
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

def get_annotation_system_fields() -> list:
    return ['name', 'owner', 'creation', 'modified', 'modified_by', 'parent', 'parentfield', 'parenttype', 'idx', 'reference_doctype', 'reference_name', 'sender', 'score', 'feedback', '_user_tags', '_comments', '_assign', '_liked_by']

def is_annotation_pending(ann) -> bool:
    meta = frappe.get_meta(ann.doctype)
    system_fields = get_annotation_system_fields()
    for field in meta.fields:
        if field.fieldname not in system_fields:
            if not getattr(ann, field.fieldname, None):
                return True
    return False

def get_annotation_response(ann) -> Union[Dict[str, Any], str]:
    meta = frappe.get_meta(ann.doctype)
    system_fields = get_annotation_system_fields()
    response = {}
    for field in meta.fields:
        if field.fieldname not in system_fields:
            response[field.fieldname] = getattr(ann, field.fieldname, "")
            
    # Return raw string if there's only one output field and it's named 'output'
    if "output" in response and len(response) == 1:
        return response["output"]
        
    return response

def get_annotation_schema(doctype_name: str) -> dict:
    meta = frappe.get_meta(doctype_name)
    system_fields = get_annotation_system_fields()
    properties = {}
    required = []
    for field in meta.fields:
        if field.fieldname not in system_fields:
            field_type = "string"
            if field.fieldtype in ["Int", "Check"]: field_type = "integer"
            elif field.fieldtype in ["Float", "Currency"]: field_type = "number"
            properties[field.fieldname] = {"type": field_type, "description": field.label or field.fieldname}
            required.append(field.fieldname)
    return {
        "name": doctype_name.replace(" ", ""),
        "schema": {
            "type": "object",
            "properties": properties,
            "required": required
        }
    }

@frappe.whitelist()
def optimize(template_doctype: str, template_name: str) -> None:
    template = frappe.get_doc(template_doctype, template_name)
    
    if not template.model:
        frappe.throw(f"No LLM Model linked to {template_doctype} {template_name}.")
    
    model_doc = frappe.get_doc("Model", template.model)
    
    if model_doc.provider and "/" not in model_doc.model_name:
        model_str = f"{model_doc.provider.lower()}/{model_doc.model_name}"
    else:
        model_str = model_doc.model_name
    
    template.db_set("status", "Optimizing")
    
    base_url, api_key = get_sift_settings()
    
    annotations = template.get("annotations", [])
    train_data = []
    
    from markdownify import markdownify
    for ann in annotations:
        if not is_annotation_pending(ann):
            messages = []
            
            sender = frappe.db.get_value("User", getattr(ann, "sender", None), ["full_name", "bio"], as_dict=True) if getattr(ann, "sender", None) else {}
            sender_name = sender.get("full_name") or ""
            sender_bio = markdownify(sender.get("bio") or "")
            if sender_name or sender_bio:
                messages.append({"role": "system", "content": f"Sender Name: {sender_name}\nSender Bio:\n{sender_bio}"})

            history_messages = get_history(ann.reference_doctype, ann.reference_name)
            messages.extend(history_messages)
            
            train_data.append({
                "trace_id": ann.name,
                "score": ann.score if getattr(ann, "score", None) is not None else 1.0,
                "messages": messages,
                "response": get_annotation_response(ann),
                "feedback": getattr(ann, "feedback", "")
            })
            
    code_fieldname = f"{template_doctype.lower().replace(' ', '_')}_code"
    agent_name = template.get(code_fieldname)

    payload = {
        "agent_name": agent_name,
        "webhook": {
            "url": f"{frappe.utils.get_url()}/api/method/frappe_cadence.utils.sift.optimize_callback",
            "events": ["completed", "failed"],
            "metadata": {
                "doctype": template_doctype,
                "name": template_name
            }
        },
        "litellm_params": {
            "model": model_str
        },
        "dspy_params": {
            "state": {
                "predict": {
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
        endpoint = f"{base_url}/agents"
        response = requests.post(endpoint, json=payload, headers=headers, timeout=10)
        response.raise_for_status()
    except Exception as e:
        template.db_set("status", "Enabled")
        frappe.throw(f"Failed to initiate optimization with Sift: {str(e)}")

@frappe.whitelist(allow_guest=True)
def optimize_callback(**kwargs) -> Dict[str, str]:
    event_type = kwargs.get("type")
    if event_type and event_type.endswith(".started"):
        return {"status": "ignored"}
        
    metadata = kwargs.get("metadata", {})
    if isinstance(metadata, str):
        import json
        try:
            metadata = json.loads(metadata)
        except Exception:
            metadata = {}
            
    template_doctype = metadata.get("doctype")
    template_name = metadata.get("name")
    
    data = kwargs.get("data", [])
    if isinstance(data, str):
        import json
        try:
            data = json.loads(data)
        except Exception:
            data = []
    
    if event_type in ("failed", "agent.failed"):
        error = kwargs.get("error") or "Unknown error"
        frappe.log_error("Sift Optimize Failed", error)
        if template_doctype and template_name:
            frappe.db.set_value(template_doctype, template_name, "status", "Enabled")
        return {"status": "failed"}
        
    if event_type in ("completed", "agent.completed"):
        agent_name = None
        if isinstance(data, list) and len(data) > 0:
            agent_name = data[0].get("agent_name")
        elif isinstance(data, dict):
            agent_name = data.get("agent_name")
            
        if not template_doctype or not template_name or not agent_name:
            frappe.throw("Invalid webhook payload")
            
        template = frappe.get_doc(template_doctype, template_name)
        template.db_set("sift_id", agent_name)
        template.db_set("status", "Disabled")
        
        return {"status": "success"}
        
    return {"status": "ignored"}

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
    
    from markdownify import markdownify
    for ann in annotations:
        if is_annotation_pending(ann):
            has_pending = True
            
            messages = []
            
            sender = frappe.db.get_value("User", getattr(ann, "sender", None), ["full_name", "bio"], as_dict=True) if getattr(ann, "sender", None) else {}
            sender_name = sender.get("full_name") or ""
            sender_bio = markdownify(sender.get("bio") or "")
            if sender_name or sender_bio:
                messages.append({"role": "system", "content": f"Sender Name: {sender_name}\nSender Bio:\n{sender_bio}"})

            history_messages = get_history(ann.reference_doctype, ann.reference_name)
            messages.extend(history_messages)
            
            payload = {
                "model": template.sift_id,
                "background": True,
                "webhook": {
                    "url": webhook_url,
                    "events": ["completed", "failed"],
                    "metadata": {
                        "name": ann.name,
                        "doctype": ann.doctype
                    }
                },
                "input": messages
            }
            
            response_schema = get_annotation_response(ann)
            if isinstance(response_schema, dict):
                payload["response_format"] = {
                    "type": "json_schema",
                    "json_schema": get_annotation_schema(ann.doctype)
                }
            
            try:
                endpoint = f"{base_url}/responses"
                response = requests.post(endpoint, json=payload, headers=headers, timeout=10)
                response.raise_for_status()
            except Exception as e:
                frappe.log_error(f"Sift Predict Error for annotation {ann.name}: {str(e)}", "Sift API")
                
    if not has_pending:
        template.db_set("status", "Disabled")
        frappe.msgprint("No pending annotations without output found.")

@frappe.whitelist(allow_guest=True)
def predict_callback(**kwargs) -> Dict[str, str]:
    event_type = kwargs.get("type")
    if event_type and event_type.endswith(".started"):
        return {"status": "ignored"}
        
    metadata = kwargs.get("metadata", {})
    if isinstance(metadata, str):
        import json
        try:
            metadata = json.loads(metadata)
        except Exception:
            metadata = {}
            
    annotation_id = metadata.get("name")
    annotation_doctype = metadata.get("doctype")
    
    data = kwargs.get("data", [])
    if isinstance(data, str):
        import json
        try:
            data = json.loads(data)
        except Exception:
            data = []
    
    if event_type in ("failed", "response.failed"):
        error = kwargs.get("error") or "Unknown error"
        frappe.log_error("Sift Predict Failed", error)
        return {"status": "failed"}
        
    if event_type in ("completed", "response.completed"):
        # Extract output_text safely from the data object
        output_text = ""
        if isinstance(data, list) and len(data) > 0:
            content_list = data[0].get("content", [])
            if content_list and isinstance(content_list, list) and len(content_list) > 0:
                output_text = content_list[0].get("text", "")
        
        if not annotation_id or not output_text or not annotation_doctype:
            frappe.throw("Invalid webhook payload")
            
        if output_text.strip().startswith("{"):
            import json
            try:
                parsed = json.loads(output_text)
                for key, value in parsed.items():
                    frappe.db.set_value(annotation_doctype, annotation_id, key, value)
            except Exception:
                # Fallback if parsing fails but it starts with '{' (should not happen with json_schema)
                if frappe.get_meta(annotation_doctype).has_field("output"):
                    frappe.db.set_value(annotation_doctype, annotation_id, "output", output_text)
        else:
            frappe.db.set_value(annotation_doctype, annotation_id, "output", output_text)
        
        return {"status": "success"}
        
    return {"status": "ignored"}
