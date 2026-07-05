import frappe
from frappe.model.document import Document

def on_update(doc: Document, method: str) -> None:
    """
    Event listener for Playbook Execution.
    Transitions the state of the Multi Channel Cadence when its playbook is completed.
    """
    if doc.reference_doctype != "Multi Channel Cadence" or not doc.reference_name:
        return

    # Check if the status transitioned to a terminal state
    if not doc.has_value_changed("status"):
        return
        
    if doc.status not in ["success", "error", "canceled"]:
        return

    # Safely fetch the Multi Channel Cadence document
    if not frappe.db.exists("Multi Channel Cadence", doc.reference_name):
        return

    mcc = frappe.get_doc("Multi Channel Cadence", doc.reference_name)

    # Only process if in Provisioning state
    if mcc.status != "Provisioning":
        return

    # Transition state based on playbook result
    if doc.status == "success":
        mcc.status = "Draft"
    elif doc.status in ["error", "canceled"]:
        mcc.status = "Error"

    # Save the document without triggering permissions
    mcc.save(ignore_permissions=True)
