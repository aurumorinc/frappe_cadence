import frappe
from frappe.model.document import Document
from frappe_controller.utils.controller import emit_event

class UserBio(Document):
    def validate(self):
        if self.has_value_changed("content") or self.is_new():
            if frappe.session.user != self.reference_user and "System Manager" not in frappe.get_roles():
                frappe.throw("You can only edit your own bio.")

    def has_permission(self, ptype="read", user=None):
        if not user:
            user = frappe.session.user
            
        # Users can view their own bio or if they are a System Manager
        if user != self.reference_user and "System Manager" not in frappe.get_roles(user):
            return False
            
        return True

    def on_update(self):
        emit_event("user_bio_created", {"reference_user": self.reference_user})

@frappe.whitelist()
def get_user_bio(reference_user, reference_cadence=None):
    """
    Returns the content of a User Bio based on precedence:
    1. Bio with reference_cadence
    2. Bio with is_default=1
    Both must be enabled.
    Returns None if no matching bio is found.
    """
    if reference_cadence:
        bio = frappe.get_all(
            "User Bio",
            filters={
                "reference_user": reference_user,
                "reference_cadence": reference_cadence,
                "enabled": 1
            },
            fields=["content"],
            limit=1
        )
        if bio:
            return bio[0].content
            
    bio = frappe.get_all(
        "User Bio",
        filters={
            "reference_user": reference_user,
            "is_default": 1,
            "enabled": 1
        },
        fields=["content"],
        limit=1
    )
    if bio:
        return bio[0].content
        
    return None
