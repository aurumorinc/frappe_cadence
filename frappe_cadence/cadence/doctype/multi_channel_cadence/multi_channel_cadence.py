import frappe
from frappe.model.document import Document
from frappe_controller.utils.background_jobs import enqueue

class MultiChannelCadence(Document):
    def on_update(self):
        # Detect if the cadence steps or linked templates have changed.
        # If changed (or if newly created and Scheduled):
        if self.status in ["Scheduled", "In Progress"]:
            # Cancel Existing Jobs
            jobs = frappe.get_all("FS Job", filters={"status": ["in", ["queued", "started"]]}, fields=["name", "arguments"])
            for job in jobs:
                import json
                try:
                    kwargs = json.loads(job.arguments)
                    if kwargs.get("cadence_name") == self.name:
                        frappe.db.set_value("FS Job", job.name, "status", "canceled")
                except Exception:
                    pass
            
            # Enqueue New Jobs
            # Fetch the master Cadence to get the schedules
            cadence = frappe.get_doc("Cadence", self.cadence_name)
            
            for idx, schedule in enumerate(cadence.cadence_schedules):
                # Check if a Communication record exists for this cadence_name and schedule_name
                comm = frappe.get_all("Communication", filters={
                    "reference_doctype": "Multi Channel Cadence",
                    "reference_name": self.name,
                    "cadence_schedule": schedule.name
                }, fields=["name", "delivery_status"])
                
                if comm:
                    if comm[0].delivery_status == "Sent":
                        continue # Skip this schedule
                    else:
                        frappe.delete_doc("Communication", comm[0].name)
                
                previous_schedule_name = cadence.cadence_schedules[idx - 1].name if idx > 0 else None
                
                enqueue(
                    "frappe_cadence.cadence.agent.process_cadence_step",
                    queue="default",
                    cadence_name=self.name,
                    schedule_name=schedule.name,
                    previous_schedule_name=previous_schedule_name
                )
