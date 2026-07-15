import frappe
from frappe.model.document import Document
from frappe_controller.utils.background_jobs import enqueue

class MultiChannelCadence(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF
        from frappe_cadence.cadence.doctype.mcc_cadence_provider.mcc_cadence_provider import MCCCadenceProvider

        cadence_for: DF.Literal["", "CRM Lead", "Contact", "Email Group"]
        cadence_name: DF.Link
        end_date: DF.Date | None
        provider: DF.Table[MCCCadenceProvider]
        recipient: DF.DynamicLink
        sender: DF.Link | None
        start_date: DF.Date
        status: DF.Literal["Provisioning", "Draft", "Scheduled", "In Progress", "Completed", "Unsubscribed", "Error"]
    # end: auto-generated types

    def before_insert(self):
        from frappe_cadence.cadence.doctype.cadence_provider.cadence_provider import resolve_providers_for_mcc
        seed = self.name if self.name else f"{self.cadence_name}-{self.recipient}"
        resolved = resolve_providers_for_mcc(seed)
        
        for channel, provider in resolved.items():
            self.append("provider", {
                "channel": channel,
                "cadence_provider": provider
            })

    def after_insert(self):
        unique_providers = list(set(row.cadence_provider for row in (self.get("provider") or []) if row.cadence_provider))
        for provider in unique_providers:
            enqueue(
                "frappe_cadence.cadence.doctype.cadence_provider.cadence_provider.broadcast_event",
                queue="low",
                provider_name=provider,
                event_method="on_mcc_created",
                mcc_doc=self
            )

    def on_update(self):
        cadence = frappe.get_doc("Cadence", self.cadence_name)
        
        # Check if providers changed
        old_doc = self.get_doc_before_save()
        if old_doc:
            old_providers = {row.channel: row.cadence_provider for row in (old_doc.get("provider") or []) if row.cadence_provider}
            current_providers = {row.channel: row.cadence_provider for row in (self.get("provider") or []) if row.cadence_provider}
            
            new_providers = {}
            for channel, provider in current_providers.items():
                if old_providers.get(channel) != provider:
                    new_providers[channel] = provider
            
            if new_providers:
                for channel, provider in new_providers.items():
                    comms = frappe.get_all("Communication", filters={
                        "reference_doctype": "Multi Channel Cadence",
                        "reference_name": self.name,
                        "communication_medium": channel,
                        "reference_cadence_provider": ["is", "not set"]
                    })
                    for comm_info in comms:
                        comm = frappe.get_doc("Communication", comm_info.name)
                        comm.reference_cadence_provider = provider
                        comm.save(ignore_permissions=True)
        
        if self.has_value_changed("status"):
            old_status = old_doc.status if old_doc else None
            unique_providers = list(set(row.cadence_provider for row in (self.get("provider") or []) if row.cadence_provider))
            for provider in unique_providers:
                enqueue(
                    "frappe_cadence.cadence.doctype.cadence_provider.cadence_provider.broadcast_event",
                    queue="low",
                    provider_name=provider,
                    event_method="on_mcc_status_changed",
                    mcc_doc=self,
                    old_status=old_status,
                    new_status=self.status
                )

        # Always enqueue steps; Frappe orchestrates delays.
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
                    "frappe_cadence.cadence.multi_channel_cadence.process_cadence_step",
                    queue="medium",
                    cadence_name=self.name,
                    schedule_name=schedule.name,
                    previous_schedule_name=previous_schedule_name
                )

def sync_lead_cadence(doc, method):
 """Update the hidden 'cadences' child table on CRM Lead for filtering purposes"""
 if getattr(doc, "cadence_for", getattr(doc, "email_cadence_for", None)) == "CRM Lead":
  if not frappe.db.exists("CRM Lead", doc.recipient):
   return

  lead = frappe.get_doc("CRM Lead", doc.recipient)
  
  if not hasattr(lead, "cadences"):
   return

  # Check if already exists in child table
  if not any(row.cadence_name == doc.cadence_name for row in lead.cadences):
   lead.append("cadences", {
    "cadence_name": doc.cadence_name
   })
   lead.save(ignore_permissions=True)

def remove_lead_cadence(doc, method):
 """Remove the reference from CRM Lead when an Email Cadence is deleted"""
 if getattr(doc, "cadence_for", getattr(doc, "email_cadence_for", None)) == "CRM Lead":
  if not frappe.db.exists("CRM Lead", doc.recipient):
   return

  lead = frappe.get_doc("CRM Lead", doc.recipient)
  if not hasattr(lead, "cadences"):
   return

  # Since we don't have the email_cadence link anymore,
  # we should check if any OTHER email cadences for this lead and cadence still exist
  other_exists = frappe.db.exists("Email Cadence", {
   "cadence_name": doc.cadence_name,
   "recipient": doc.recipient,
   "name": ("!=", doc.name)
  })

  if not other_exists:
   lead.set("cadences", [
    row for row in lead.cadences if row.cadence_name != doc.cadence_name
   ])
   lead.save(ignore_permissions=True)
