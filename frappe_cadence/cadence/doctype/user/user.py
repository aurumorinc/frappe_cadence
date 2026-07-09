import frappe

def validate_bio(doc, method):
    if doc.has_value_changed("bio"):
        if frappe.session.user != doc.name and "System Manager" not in frappe.get_roles():
            frappe.throw("You can only edit your own bio.")
