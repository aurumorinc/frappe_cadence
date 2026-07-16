import frappe
from frappe.model.document import Document

class LinkedInTemplate(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF
        from frappe_cadence.cadence.doctype.linkedin_template_annotation.linkedin_template_annotation import LinkedinTemplateAnnotation

        annotations: DF.Table[LinkedinTemplateAnnotation]
        linkedin_template_code: DF.Data | None
        message: DF.TextEditor | None
        sift_id: DF.Data | None
        status: DF.Literal["Enabled", "Prompt", "Disabled"]
        title: DF.Data
    # end: auto-generated types

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
