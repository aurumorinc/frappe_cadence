import frappe
import requests
import json
import urllib.parse
import hmac
import hashlib
import base64
from frappe.utils import add_months, today, get_url
from frappe.model.document import Document
from frappe_controller.utils.background_jobs import enqueue
from frappe_controller.utils.controller import wait_for_event, emit_event

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
                    event_method="on_mcc_update",
                    mcc_doc=self,
                    old_status=old_status,
                    new_status=self.status
                )

            if self.status in ["Scheduled", "In Progress"]:
                existing_jobs = False
                jobs = frappe.get_all("FS Job", filters={"status": ["in", ["queued", "started", "deferred"]]}, fields=["name", "arguments"])
                for job in jobs:
                    import json
                    try:
                        kwargs = json.loads(job.arguments)
                        if kwargs.get("cadence_name") == self.name:
                            existing_jobs = True
                            break
                    except Exception:
                        pass
                
                if not existing_jobs:
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
                            "frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.process_schedule",
                            queue="medium",
                            cadence_name=self.name,
                            schedule_name=schedule.name,
                            previous_schedule_name=previous_schedule_name
                        )
                else:
                    if self.status == "Scheduled":
                        emit_event("mcc_scheduled", {"doctype": self.doctype, "name": self.name})
                    elif self.status == "In Progress":
                        emit_event("mcc_in_progress", {"doctype": self.doctype, "name": self.name})

def on_update(doc, method):
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

def on_trash(doc, method):
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

def process_schedule(cadence_name, schedule_name, previous_schedule_name=None):
    """
    Processes a single step in a multi-channel cadence.
    Must be idempotent as it executes from line 1 when resumed.
    """
    # 1. MCC State Check
    mcc = frappe.get_doc("Multi Channel Cadence", cadence_name)
    if mcc.status not in ["Scheduled", "In Progress"]:
        wait_for_event(
            event_key="mcc_scheduled" if mcc.status != "In Progress" else "mcc_in_progress",
            condition=f"argument.get('doctype') == 'Multi Channel Cadence' and argument.get('name') == '{cadence_name}'"
        )
        return

    # 2. Wait for Previous Step
    if previous_schedule_name:
        prev_comm = frappe.get_all("Communication", filters={
            "reference_doctype": "Multi Channel Cadence",
            "reference_name": cadence_name,
            "cadence_schedule": previous_schedule_name,
            "delivery_status": ["in", ["Scheduled", "Sent"]]
        })
        if not prev_comm:
            wait_for_event(
                "cadence_step_completed",
                condition=f"argument.get('cadence_name') == '{cadence_name}' and argument.get('schedule_name') == '{previous_schedule_name}'"
            )
            return

    # 3. Idempotency Check
    curr_comm = frappe.get_all("Communication", filters={
        "reference_doctype": "Multi Channel Cadence",
        "reference_name": cadence_name,
        "cadence_schedule": schedule_name,
        "delivery_status": ["in", ["Scheduled", "Sent"]]
    })
    if curr_comm:
        emit_event("cadence_step_completed", {"cadence_name": cadence_name, "schedule_name": schedule_name})
        return

    # 4. Template State Check & Process Template
    schedule = frappe.get_doc("Cadence Multi Channel Schedule", schedule_name)
    
    template_doctype = f"{schedule.reference_doctype}"
    template_name = schedule.reference_name
    template = frappe.get_doc(template_doctype, template_name)
    
    if template.status == "Disabled":
        event_key = f"{template_doctype.lower().replace(' ', '_')}_enabled"
        wait_for_event(
            event_key=event_key,
            condition=f"argument.get('doctype') == '{template_doctype}' and argument.get('name') == '{template_name}' and argument.get('enabled') == 1"
        )
        return

    channel = template_doctype.replace(" Template", "")

    reference_cadence_provider = None
    for row in (mcc.get("provider") or []):
        if row.channel == channel:
            reference_cadence_provider = row.cadence_provider
            break

    if template.status == "Enabled":
        comm = frappe.get_doc({
            "doctype": "Communication",
            "communication_medium": channel,
            "subject": getattr(template, "subject", template.get("title", f"{channel} Message")),
            "content": template.get("message") or template.get("response"),
            "reference_doctype": "Multi Channel Cadence",
            "reference_name": cadence_name,
            "cadence_schedule": schedule_name,
            "status": "Open",
            "delivery_status": "Scheduled",
            "reference_cadence_provider": reference_cadence_provider
        })
        comm.insert(ignore_permissions=True)
        emit_event("cadence_step_completed", {"cadence_name": cadence_name, "schedule_name": schedule_name})
        return

    if template.status == "Prompt":
        draft_comm = frappe.get_all("Communication", filters={
            "reference_doctype": "Multi Channel Cadence",
            "reference_name": cadence_name,
            "cadence_schedule": schedule_name,
            "status": "Open"
        })
        
        if not draft_comm:
            comm = frappe.get_doc({
                "doctype": "Communication",
                "communication_medium": channel,
                "subject": f"Draft {channel} Message",
                "reference_doctype": "Multi Channel Cadence",
                "reference_name": cadence_name,
                "cadence_schedule": schedule_name,
                "status": "Open",
                "reference_cadence_provider": reference_cadence_provider
            })
            comm.insert(ignore_permissions=True)
            comm_name = comm.name
            
            # Construct AI Agent payload
            cadence = frappe.get_doc("Multi Channel Cadence", cadence_name)
            lead = frappe.get_doc(cadence.cadence_for, cadence.recipient)
            
            schema_properties = {
                "content": {
                    "type": "string",
                    "description": "The main body content of the message"
                }
            }
            required_fields = ["content"]
            
            if channel == "Email":
                schema_properties["subject"] = {
                    "type": "string",
                    "description": "The subject of the message"
                }
                required_fields.append("subject")
                
            payload = {
                "metadata": {
                    "name": comm_name
                },
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "communication_generation",
                        "strict": True,
                        "schema": {
                            "type": "object",
                            "properties": schema_properties,
                            "required": required_fields,
                            "additionalProperties": False
                        }
                    }
                },
            }
            
            from markdownify import markdownify
            from frappe_cadence.cadence.doctype.history.history import get_history
            from frappe_cadence.cadence.doctype.user_bio.user_bio import get_user_bio
            
            sender_bio_content = get_user_bio(mcc.owner, cadence_name)
            if not sender_bio_content:
                wait_for_event("user_bio_created", condition=f"argument.get('reference_user') == '{mcc.owner}'")
                return
                
            sender = frappe.db.get_value("User", mcc.owner, ["full_name"], as_dict=True) or {}
            sender_name = sender.get("full_name") or ""
            sender_bio = markdownify(sender_bio_content)
            
            payload["input"] = []
            if sender_name or sender_bio:
                payload["input"].append({
                    "role": "system",
                    "content": f"Sender Name: {sender_name}\nSender Bio:\n{sender_bio}"
                })
            
            # Fetch and format History records
            three_months_ago = add_months(today(), -3)
            history_messages = get_history(cadence.cadence_for, cadence.recipient, since_date=three_months_ago)
            payload["input"].extend(history_messages)

            # Use /responses endpoint instead of /agents and map cadence model
            payload["model"] = cadence.sift_id or "default-model"
            
            cache_val = frappe.cache().get_value(f"ai_req:{cadence_name}:{schedule_name}")
            
            if not cache_val:
                sift_settings = frappe.get_single("Sift Settings")
                sift_base_url = sift_settings.sift_base_url
                sift_api_key = sift_settings.get_password("sift_api_key")
                
                if sift_base_url:
                    headers = {"Content-Type": "application/json"}
                    if sift_api_key:
                        headers["Authorization"] = f"Bearer {sift_api_key}"
                    
                    # Add webhook info to payload so Sift knows where to callback
                    webhook_url = get_url(f"/api/method/frappe_cadence.cadence.{channel.lower()}_template.callback")
                    payload["background"] = True
                    payload["webhook"] = {
                        "url": webhook_url,
                        "events": ["completed", "failed"]
                    }

                    payload_json = json.dumps(payload, separators=(',', ':'))
                    
                    try:
                        requests.post(f"{sift_base_url}/responses", headers=headers, data=payload_json, timeout=10)
                        frappe.cache().set_value(f"ai_req:{cadence_name}:{schedule_name}", 1, expires_in_sec=86400)
                    except Exception as e:
                        frappe.log_error(title="Agent Error", message=f"Failed to send task to Agent: {str(e)}")
                        return
                else:
                    frappe.log_error(title="Sift Configuration Error", message="Sift Base URL not configured.")
                    return
        else:
            comm_name = draft_comm[0].name
            
        wait_for_event("callback", condition=f"argument.get('communication_id') == '{comm_name}'")
