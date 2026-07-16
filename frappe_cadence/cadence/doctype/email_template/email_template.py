import frappe

def before_save(doc, method):
	if doc.status == "Disabled":
		doc.enabled = 0
	else:
		doc.enabled = 1

def on_update(doc, method=None):
    doc_before_save = doc.get_doc_before_save()
    if doc_before_save and doc_before_save.status != doc.status:
        from frappe_controller.utils.controller import emit_event
        event_key = f"{doc.doctype.lower().replace(' ', '_')}_enabled"
        emit_event(
            key=event_key,
            argument={
                "doctype": doc.doctype,
                "name": doc.name,
                "enabled": 1 if doc.status in ["Enabled", "Prompt"] else 0
            }
        )
