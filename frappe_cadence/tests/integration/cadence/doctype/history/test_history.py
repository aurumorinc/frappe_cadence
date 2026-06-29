# Copyright (c) 2024, Roo and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase

class TestHistory(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()

	@classmethod
	def tearDownClass(cls):
		frappe.db.rollback()
		super().tearDownClass()

	def tearDown(self):
		frappe.db.rollback()
		super().tearDown()

	def test_history_schema(self):
		# Create a dummy reference document or just use a generic one
		# History can be created standalone to test the schema
		history_doc = frappe.get_doc({
			"doctype": "History",
			"url": "https://example.com",
			"content": "Test history content",
			"images": [
				{
					"image": "/files/test_image1.png"
				},
				{
					"image": "/files/test_image2.png"
				}
			]
		}).insert()

		# Verify that the URL field was saved correctly
		self.assertEqual(history_doc.url, "https://example.com")
		
		# Verify that the child table is correctly populated
		self.assertEqual(len(history_doc.images), 2)
		self.assertEqual(history_doc.images[0].image, "/files/test_image1.png")
		self.assertEqual(history_doc.images[1].image, "/files/test_image2.png")
