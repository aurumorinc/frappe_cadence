import frappe
from frappe.tests import IntegrationTestCase


class TestTemplates(IntegrationTestCase):
    @classmethod
    def tearDownClass(cls):
        frappe.db.rollback()
        super().tearDownClass()

    def test_sift_id_in_linkedin_template(self):
        doc = frappe.get_doc({
            "doctype": "LinkedIn Template",
            "title": "_Test LinkedIn Template",
            "status": "Enabled",
            "message": "Hello from LinkedIn",
            "sift_id": "sift_lin_123"
        }).insert(ignore_permissions=True)
        
        reloaded_doc = frappe.get_doc("LinkedIn Template", doc.name)
        self.assertEqual(reloaded_doc.sift_id, "sift_lin_123")
        
        meta = frappe.get_meta("LinkedIn Template")
        field = meta.get_field("sift_id")
        self.assertIsNotNone(field)
        self.assertTrue(field.hidden)

    def test_sift_id_in_sms_template(self):
        doc = frappe.get_doc({
            "doctype": "SMS Template",
            "title": "_Test SMS Template",
            "status": "Enabled",
            "message": "Hello from SMS",
            "sift_id": "sift_sms_123"
        }).insert(ignore_permissions=True)
        
        reloaded_doc = frappe.get_doc("SMS Template", doc.name)
        self.assertEqual(reloaded_doc.sift_id, "sift_sms_123")
        
        meta = frappe.get_meta("SMS Template")
        field = meta.get_field("sift_id")
        self.assertIsNotNone(field)
        self.assertTrue(field.hidden)

    def test_sift_id_in_whatsapp_template(self):
        doc = frappe.get_doc({
            "doctype": "WhatsApp Template",
            "title": "_Test WhatsApp Template",
            "status": "Enabled",
            "message": "Hello from WhatsApp",
            "sift_id": "sift_wa_123"
        }).insert(ignore_permissions=True)
        
        reloaded_doc = frappe.get_doc("WhatsApp Template", doc.name)
        self.assertEqual(reloaded_doc.sift_id, "sift_wa_123")
        
        meta = frappe.get_meta("WhatsApp Template")
        field = meta.get_field("sift_id")
        self.assertIsNotNone(field)
        self.assertTrue(field.hidden)

    def test_sift_id_in_email_template(self):
        doc = frappe.get_doc({
            "doctype": "Email Template",
            "name": "_Test Email Template",
            "subject": "_Test Email Subject",
            "response": "Hello from Email",
            "sift_id": "sift_email_123"
        }).insert(ignore_permissions=True)
        
        reloaded_doc = frappe.get_doc("Email Template", doc.name)
        self.assertEqual(reloaded_doc.sift_id, "sift_email_123")
        
        meta = frappe.get_meta("Email Template")
        field = meta.get_field("sift_id")
        self.assertIsNotNone(field)
        self.assertTrue(field.hidden)