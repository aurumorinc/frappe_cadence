import frappe
from frappe.tests import IntegrationTestCase
from frappe.exceptions import ValidationError

class TestUser(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if not frappe.db.exists("User", "test_bio_user1@example.com"):
            frappe.get_doc({
                "doctype": "User",
                "email": "test_bio_user1@example.com",
                "first_name": "Test",
                "last_name": "Bio1",
                "send_welcome_email": 0
            }).insert(ignore_permissions=True)
            
        if not frappe.db.exists("User", "test_bio_user2@example.com"):
            frappe.get_doc({
                "doctype": "User",
                "email": "test_bio_user2@example.com",
                "first_name": "Test",
                "last_name": "Bio2",
                "send_welcome_email": 0
            }).insert(ignore_permissions=True)
            
        frappe.db.commit()

    @classmethod
    def tearDownClass(cls):
        frappe.db.rollback()
        # Clean up to avoid orphans
        frappe.db.delete("User", {"email": ["in", ["test_bio_user1@example.com", "test_bio_user2@example.com"]]})
        frappe.db.commit()
        super().tearDownClass()
        
    def test_bio_privacy_validation(self):
        user1 = frappe.get_doc("User", "test_bio_user1@example.com")
        
        # Test saving as self
        frappe.set_user("test_bio_user1@example.com")
        user1.bio = "My personal bio"
        user1.save(ignore_permissions=True)
        self.assertEqual(user1.bio, "My personal bio")
        
        # Test saving as other non-system manager
        frappe.set_user("test_bio_user2@example.com")
        user1 = frappe.get_doc("User", "test_bio_user1@example.com")
        user1.bio = "Modified by someone else"
        
        with self.assertRaises(ValidationError):
            user1.save(ignore_permissions=True)
            
        # Test saving as System Manager
        frappe.set_user("Administrator")
        user1 = frappe.get_doc("User", "test_bio_user1@example.com")
        user1.bio = "Modified by admin"
        user1.save(ignore_permissions=True)
        self.assertEqual(user1.bio, "Modified by admin")
