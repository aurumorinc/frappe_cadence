import frappe
from frappe_controller.utils.background_jobs import enqueue

def on_communication_update(doc, method=None):
    if doc.reference_doctype == "Multi Channel Cadence" and doc.reference_name:
        provider_name = doc.get("reference_cadence_provider")
        if provider_name:
            if doc.has_value_changed("delivery_status"):
                old_status = doc.get_doc_before_save().delivery_status if doc.get_doc_before_save() else None
                new_status = doc.delivery_status
                enqueue(
                    "frappe_cadence.cadence.doctype.cadence_provider.cadence_provider.broadcast_event",
                    queue="low",
                    provider_name=provider_name,
                    event_method="on_communication_status_changed",
                    comm_doc=doc,
                    old_status=old_status,
                    new_status=new_status,
                    now=frappe.flags.in_test
                )

def on_communication_create(doc, method=None):
    if doc.reference_doctype == "Multi Channel Cadence" and doc.reference_name:
        provider_name = doc.get("reference_cadence_provider")
        if provider_name:
            enqueue(
                "frappe_cadence.cadence.doctype.cadence_provider.cadence_provider.broadcast_event",
                queue="low",
                provider_name=provider_name,
                event_method="on_communication_created",
                comm_doc=doc,
                now=frappe.flags.in_test
            )
