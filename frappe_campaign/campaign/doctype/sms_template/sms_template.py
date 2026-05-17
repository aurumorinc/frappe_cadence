import frappe
from frappe.model.document import Document

class SMSTemplate(Document):
    def on_update(self):
        campaigns = frappe.get_all("Multi Channel Campaign", filters={"status": ["in", ["Scheduled", "In Progress"]]}, fields=["name", "campaign_name"])
        for camp in campaigns:
            master_campaign = frappe.get_doc("Campaign", camp.campaign_name)
            for schedule in master_campaign.campaign_schedules:
                if schedule.reference_doctype == "SMS Template" and schedule.reference_name == self.name:
                    doc = frappe.get_doc("Multi Channel Campaign", camp.name)
                    doc.save(ignore_permissions=True)
                    break
