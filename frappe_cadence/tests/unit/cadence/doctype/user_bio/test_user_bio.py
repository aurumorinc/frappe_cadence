import frappe
from frappe.tests import UnitTestCase
from unittest.mock import patch

class TestUserBio(UnitTestCase):
    def get_test_doc(self, reference_user):
        from frappe_cadence.cadence.doctype.user_bio.user_bio import UserBio
        doc = UserBio({"doctype": "User Bio", "reference_user": reference_user})
        # Override is_new and has_value_changed for unit testing without db
        doc.is_new = lambda: True
        doc.has_value_changed = lambda x: True
        return doc

    def test_bio_privacy_validation_non_owner(self):
        doc = self.get_test_doc("owner@test.com")

        with patch("frappe.session") as mock_session:
            mock_session.user = "other@test.com"
            with patch("frappe.get_roles", return_value=["Blogger"]):
                with self.assertRaises(frappe.exceptions.ValidationError) as context:
                    doc.validate()
                self.assertIn("You can only edit your own bio.", str(context.exception))

    def test_bio_privacy_validation_owner(self):
        doc = self.get_test_doc("owner@test.com")

        with patch("frappe.session") as mock_session:
            mock_session.user = "owner@test.com"
            with patch("frappe.get_roles", return_value=["Blogger"]):
                try:
                    doc.validate()
                except frappe.exceptions.ValidationError:
                    self.fail("validate() raised ValidationError unexpectedly!")

    def test_bio_privacy_validation_admin(self):
        doc = self.get_test_doc("owner@test.com")

        with patch("frappe.session") as mock_session:
            mock_session.user = "other@test.com"
            with patch("frappe.get_roles", return_value=["System Manager"]):
                try:
                    doc.validate()
                except frappe.exceptions.ValidationError:
                    self.fail("validate() raised ValidationError unexpectedly!")

    def test_bio_read_privacy_non_owner(self):
        doc = self.get_test_doc("owner@test.com")

        with patch("frappe.session") as mock_session:
            mock_session.user = "other@test.com"
            with patch("frappe.get_roles", return_value=["Blogger"]):
                self.assertFalse(doc.has_permission("read"))

    def test_bio_read_privacy_owner_or_admin(self):
        doc = self.get_test_doc("owner@test.com")

        # As owner
        with patch("frappe.session") as mock_session:
            mock_session.user = "owner@test.com"
            with patch("frappe.get_roles", return_value=["Blogger"]):
                self.assertTrue(doc.has_permission("read"))

        # As System Manager
        with patch("frappe.session") as mock_session:
            mock_session.user = "admin@test.com"
            with patch("frappe.get_roles", return_value=["System Manager"]):
                self.assertTrue(doc.has_permission("read"))

    def test_get_user_bio_precedence(self):
        from frappe_cadence.cadence.doctype.user_bio.user_bio import get_user_bio
        
        with patch("frappe.get_all") as mock_get_all:
            # Scenario 1: Both specific and default bio exist
            def side_effect_get_all(doctype, filters, **kwargs):
                if filters.get("reference_cadence"):
                    return [frappe._dict(content="Cadence Bio")]
                return [frappe._dict(content="Default Bio")]
                
            mock_get_all.side_effect = side_effect_get_all
            
            content = get_user_bio("owner@test.com", "Cadence 1")
            self.assertEqual(content, "Cadence Bio")
            
            # Scenario 2: Only default bio exists
            def side_effect_get_all_default_only(doctype, filters, **kwargs):
                if filters.get("reference_cadence"):
                    return []
                return [frappe._dict(content="Default Bio")]
                
            mock_get_all.side_effect = side_effect_get_all_default_only
            
            content = get_user_bio("owner@test.com", "Cadence 1")
            self.assertEqual(content, "Default Bio")
            
            # Scenario 3: No bio exists
            mock_get_all.side_effect = lambda *args, **kwargs: []
            
            content = get_user_bio("owner@test.com", "Cadence 1")
            self.assertIsNone(content)
