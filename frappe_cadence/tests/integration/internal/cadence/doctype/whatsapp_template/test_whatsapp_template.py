# Copyright (c) 2026, Aurumor and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase


# On IntegrationTestCase, the doctype test records and all
# link-field test record dependencies are recursively loaded
# Use these module variables to add/remove to/from that list
EXTRA_TEST_RECORD_DEPENDENCIES = []  # eg. ["User"]
IGNORE_TEST_RECORD_DEPENDENCIES = []  # eg. ["User"]



class IntegrationTestWhatsAppTemplate(IntegrationTestCase):
	@classmethod
	def tearDownClass(cls):
		frappe.db.rollback()
		super().tearDownClass()

	"""
	Integration tests for WhatsAppTemplate.
	Use this class for testing interactions between multiple components.
	"""

	def test_sift_id_in_whatsapp_template(self):
		import frappe
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
