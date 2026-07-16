# Copyright (c) 2024, Roo and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class History(Document):
	pass

@frappe.whitelist()
def get_history(reference_doctype: str, reference_name: str, since_date=None) -> list:
    from frappe.utils import add_months, today
    
    if not since_date:
        since_date = add_months(today(), -3)
        
    or_filters = {
        reference_doctype: reference_name
    }
    if reference_doctype == "CRM Lead":
        lead = frappe.get_doc("CRM Lead", reference_name)
        if lead.organization:
            or_filters["CRM Organization"] = lead.organization
            
    histories = []
    for ref_dt, ref_name in or_filters.items():
        histories.extend(frappe.get_all(
            "History",
            filters={"reference_doctype": ref_dt, "reference_name": ref_name, "creation": [">=", since_date]},
            fields=["name", "markdown", "screenshot", "creation"],
            order_by="creation asc"
        ))
        
    # Sort the combined histories by creation date
    histories.sort(key=lambda x: x.creation)
    
    messages = []
    from markdownify import markdownify
    for h in histories:
        content_blocks = []
        if h.markdown:
            content_blocks.append({"type": "text", "text": markdownify(h.markdown)})
            
        if h.screenshot:
            try:
                file_doc = frappe.get_doc("File", {"file_url": h.screenshot})
                content_blocks.append({
                    "type": "image_url",
                    "image_url": {"url": file_doc.presigned_url}
                })
            except frappe.DoesNotExistError:
                pass

        if content_blocks:
            messages.append({"role": "user", "content": content_blocks})
            
    return messages
