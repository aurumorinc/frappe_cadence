import frappe
from frappe.model.document import Document

class SMSTemplate(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF
        from frappe_cadence.cadence.doctype.sms_template_annotation.sms_template_annotation import SMSTemplateAnnotation

        annotations: DF.Table[SMSTemplateAnnotation]
        message: DF.TextEditor | None
        sift_id: DF.Data | None
        sms_template_code: DF.Data | None
        status: DF.Literal["Enabled", "Prompt", "Disabled"]
        title: DF.Data
    # end: auto-generated types

    def on_update(self):
        cadences = frappe.get_all("Multi Channel Cadence", filters={"status": ["in", ["Scheduled", "In Progress"]]}, fields=["name", "cadence_name"])
        for camp in cadences:
            master_cadence = frappe.get_doc("Cadence", camp.cadence_name)
            for schedule in master_cadence.cadence_schedules:
                if schedule.reference_doctype == "SMS Template" and schedule.reference_name == self.name:
                    doc = frappe.get_doc("Multi Channel Cadence", camp.name)
                    doc.save(ignore_permissions=True)
                    break
