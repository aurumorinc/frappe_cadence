# Copyright (c) 2024, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
import hashlib
from typing import Dict, Optional

class CadenceProvider(Document):
    pass

class CadenceProviderBase:
    """
    Abstract base class for Cadence Providers.
    Any integration (Apollo, Outreach, etc.) must implement this interface.
    """
    
    def on_mcc_created(self, mcc_doc):
        pass

    def on_mcc_status_changed(self, mcc_doc, old_status, new_status):
        pass

    def on_cadence_updated(self, cadence_doc):
        pass

    def on_communication_created(self, comm_doc):
        pass

    def on_communication_status_changed(self, comm_doc, old_status, new_status):
        pass

    @classmethod
    def report_event(cls, event_type: str, context: dict, data: dict = None):
        """
        Providers call this method when an external event occurs (e.g. from a webhook).
        This method is responsible for updating the internal Frappe state based on the event.
        
        event_type: 'message_replied', 'bounce', 'message_sent', 'message_opened', etc.
        context: e.g. {"mcc_name": "MCC-001", "communication_name": "COMM-001"}
        data: The raw payload from the provider (optional)
        """
        mcc_name = context.get("mcc_name")
        comm_name = context.get("communication_name")
        
        if event_type == "message_replied":
            if mcc_name:
                frappe.db.set_value("Multi Channel Cadence", mcc_name, "status", "Replied")
                frappe.get_doc({
                    "doctype": "History",
                    "reference_doctype": "Multi Channel Cadence",
                    "reference_name": mcc_name,
                    "content": "Replied",
                    "url": data.get("url", "https://example.com") if data else "https://example.com"
                }).insert(ignore_permissions=True)
                
        elif event_type == "bounce":
            if mcc_name:
                frappe.db.set_value("Multi Channel Cadence", mcc_name, "status", "Bounced")
                frappe.get_doc({
                    "doctype": "History",
                    "reference_doctype": "Multi Channel Cadence",
                    "reference_name": mcc_name,
                    "content": "Bounced",
                    "url": data.get("url", "https://example.com") if data else "https://example.com"
                }).insert(ignore_permissions=True)
                
        elif event_type in ["message_sent", "message_opened"]:
            if comm_name:
                status_field = "delivery_status" if event_type == "message_sent" else "read_status"
                new_status = "Sent" if event_type == "message_sent" else "Read"
                
                frappe.db.set_value("Communication", comm_name, status_field, new_status)
                
                if mcc_name:
                    frappe.get_doc({
                        "doctype": "History",
                        "reference_doctype": "Multi Channel Cadence",
                        "reference_name": mcc_name,
                        "content": "Message Sent" if event_type == "message_sent" else "Message Opened",
                        "url": data.get("url", "https://example.com") if data else "https://example.com"
                    }).insert(ignore_permissions=True)


def get_provider_instance(provider_name):
    hooks = frappe.get_hooks("cadence_providers")
    if not hooks or provider_name not in hooks:
        raise ValueError(_("Provider {0} not found in cadence_providers hooks").format(provider_name))
    
    class_path = hooks[provider_name]
    if isinstance(class_path, list):
        class_path = class_path[-1] # take the last one if multiple are defined
        
    provider_class = frappe.get_attr(class_path)
    return provider_class()


def broadcast_event(provider_name, event_method, *args, **kwargs):
    try:
        provider = get_provider_instance(provider_name)
        method = getattr(provider, event_method)
        method(*args, **kwargs)
    except Exception as e:
        frappe.log_error(title=f"Cadence Provider Event Error: {event_method}", message=frappe.get_traceback())


def resolve_providers_for_mcc(mcc_name: str) -> Dict[str, str]:
    """
    Reads mappings from active Cadence Providers globally, groups by channel, applies a stable hash of mcc_name
    to pick a provider based on priority, and returns a dict of selected providers:
    {"Email": "Apollo"}
    """
    if not mcc_name:
        return {}

    active_providers = frappe.get_all(
        "Cadence Provider",
        filters={"enabled": 1},
        fields=["name"]
    )

    if not active_providers:
        return {}
        
    cadence_providers = []
    for ap in active_providers:
        channels = frappe.get_all(
            "Channel Cadence Provider",
            filters={"parent": ap.name, "parenttype": "Cadence Provider"},
            fields=["channel", "priority"]
        )
        for c in channels:
            cadence_providers.append({
                "provider": ap.name,
                "channel": c.channel,
                "priority": c.priority
            })

    if not cadence_providers:
        return {}

    # Group by channel
    channel_groups = {}
    for p in cadence_providers:
        channel = p.get("channel")
        priority = int(p.get("priority") or 0)
        if priority <= 0:
            continue
            
        if channel not in channel_groups:
            channel_groups[channel] = []
        channel_groups[channel].append({
            "provider": p.get("provider"),
            "priority": priority
        })

    # Sort each group for deterministic ordering
    for channel in channel_groups:
        channel_groups[channel].sort(key=lambda x: x["provider"])

    # Pick provider based on hash
    # Use MD5 to get a stable uniform hash of mcc_name
    hash_digest = hashlib.md5(mcc_name.encode('utf-8')).hexdigest()
    # Convert first 8 hex characters to an integer (large enough)
    hash_int = int(hash_digest[:8], 16)

    resolved_providers = {}
    
    for channel, providers in channel_groups.items():
        total_priority = sum(p["priority"] for p in providers)
        if total_priority == 0:
            continue
            
        # The remainder will be used to select the bucket
        ticket = hash_int % total_priority
        
        current_sum = 0
        selected = None
        for p in providers:
            current_sum += p["priority"]
            if ticket < current_sum:
                selected = p["provider"]
                break
                
        if selected:
            resolved_providers[channel] = selected

    return resolved_providers
