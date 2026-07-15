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
			"markdown": "Test history content",
			"html": "<p>Test history content</p>",
			"screenshot": "/files/test_image.png"
		}).insert()

		# Verify that fields were saved correctly
		self.assertEqual(history_doc.url, "https://example.com")
		self.assertEqual(history_doc.markdown, "Test history content")
		self.assertEqual(history_doc.screenshot, "/files/test_image.png")

	def test_history_group_schema(self):
		history_doc = frappe.get_doc({
			"doctype": "History",
			"url": "https://example.com/hist1",
			"markdown": "Content"
		}).insert()

		group_doc = frappe.get_doc({
			"doctype": "History Group",
			"url": "https://example.com",
			"history": [
				{
					"history": history_doc.name
				}
			]
		}).insert()

		self.assertEqual(group_doc.url, "https://example.com")
		self.assertEqual(len(group_doc.history), 1)
		self.assertEqual(group_doc.history[0].history, history_doc.name)
