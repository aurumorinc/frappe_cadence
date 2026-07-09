import frappe
from frappe.tests import UnitTestCase
from unittest.mock import patch, MagicMock
from frappe_cadence.cadence.doctype.user.user import validate_bio

class TestUser(UnitTestCase):
    def test_bio_privacy_validation_non_owner(self):
        doc = MagicMock()
        doc.has_value_changed.return_value = True
        doc.name = "test@example.com"
        
        with patch("frappe.session") as mock_session:
            mock_session.user = "other@example.com"
            with patch("frappe.get_roles") as mock_get_roles:
                mock_get_roles.return_value = ["Blogger"]
                
                with self.assertRaises(frappe.exceptions.ValidationError) as context:
                    validate_bio(doc, "validate")
                
                self.assertIn("You can only edit your own bio.", str(context.exception))

    def test_bio_privacy_validation_owner(self):
        doc = MagicMock()
        doc.has_value_changed.return_value = True
        doc.name = "test@example.com"
        
        with patch("frappe.session") as mock_session:
            mock_session.user = "test@example.com"
            with patch("frappe.get_roles") as mock_get_roles:
                mock_get_roles.return_value = ["Blogger"]
                
                try:
                    validate_bio(doc, "validate")
                except frappe.exceptions.ValidationError:
                    self.fail("validate_bio raised ValidationError unexpectedly!")

    def test_bio_privacy_validation_admin(self):
        doc = MagicMock()
        doc.has_value_changed.return_value = True
        doc.name = "test@example.com"
        
        with patch("frappe.session") as mock_session:
            mock_session.user = "admin@example.com"
            with patch("frappe.get_roles") as mock_get_roles:
                mock_get_roles.return_value = ["System Manager"]
                
                try:
                    validate_bio(doc, "validate")
                except frappe.exceptions.ValidationError:
                    self.fail("validate_bio raised ValidationError unexpectedly!")
