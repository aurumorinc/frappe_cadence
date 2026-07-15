import frappe
from frappe.tests import IntegrationTestCase
from frappe_cadence.cadence.doctype.user_bio.user_bio import get_user_bio

class TestUserBioIntegration(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Ensure we have a test user
        if not frappe.db.exists("User", "test_bio_user@example.com"):
            frappe.get_doc({
                "doctype": "User",
                "email": "test_bio_user@example.com",
                "first_name": "Test",
                "last_name": "Bio User",
                "send_welcome_email": 0
            }).insert(ignore_permissions=True)

    @classmethod
    def tearDownClass(cls):
        frappe.db.rollback()
        super().tearDownClass()

    def tearDown(self):
        frappe.db.rollback()
        super().tearDown()

    def test_get_user_bio_integration(self):
        cadence_doc = frappe.get_doc({
            "doctype": "Cadence",
            "cadence_name": "Test Cadence",
        }).insert(ignore_permissions=True)
            
        # 1. Create a default bio
        default_bio = frappe.get_doc({
            "doctype": "User Bio",
            "reference_user": "test_bio_user@example.com",
            "content": "This is the default bio.",
            "is_default": 1,
            "enabled": 1
        }).insert(ignore_permissions=True)

        # 2. Create a cadence-specific bio
        cadence_bio = frappe.get_doc({
            "doctype": "User Bio",
            "reference_user": "test_bio_user@example.com",
            "reference_cadence": cadence_doc.name,
            "content": "This is the cadence specific bio.",
            "enabled": 1
        }).insert(ignore_permissions=True)

        # 3. Test retrieving the cadence-specific bio
        fetched_cadence_bio = get_user_bio("test_bio_user@example.com", cadence_doc.name)
        self.assertEqual(fetched_cadence_bio, "This is the cadence specific bio.")

        # 4. Test retrieving the default bio (when no cadence matches or none provided)
        fetched_default_bio = get_user_bio("test_bio_user@example.com")
        self.assertEqual(fetched_default_bio, "This is the default bio.")
        
        # Test retrieving default bio even when a cadence is provided but doesn't exist
        fetched_fallback_bio = get_user_bio("test_bio_user@example.com", "Non-existent Cadence")
        self.assertEqual(fetched_fallback_bio, "This is the default bio.")

        # 5. Test when neither exists
        fetched_none = get_user_bio("non_existent_user@example.com", "Test Cadence")
        self.assertIsNone(fetched_none)
