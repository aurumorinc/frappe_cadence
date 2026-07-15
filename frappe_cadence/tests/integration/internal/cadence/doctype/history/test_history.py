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

	def test_get_history_integration(self):
		from frappe.utils import add_months, today
		from frappe_cadence.cadence.doctype.history.history import get_history
		
		# Create a dummy CRM Lead
		lead = frappe.get_doc({
			"doctype": "CRM Lead",
			"first_name": "Test History Lead"
		}).insert(ignore_permissions=True)
		
		# Create a History record
		hist1 = frappe.get_doc({
			"doctype": "History",
			"reference_doctype": "CRM Lead",
			"reference_name": lead.name,
			"markdown": "**Bold interaction**"
		}).insert(ignore_permissions=True)
		
		# Test fetch
		since = add_months(today(), -1)
		messages = get_history("CRM Lead", lead.name, since_date=since)
		
		# Validate that messages are constructed correctly
		self.assertTrue(len(messages) >= 1)
		
		# Markdown should be converted to HTML (since get_history uses markdownify)
		# Wait, markdownify converts HTML to Markdown. If the field is called "markdown"
		# and it contains markdown, passing it to markdownify might not change it much,
		# but let's just check if the text is present in the output.
		
		# The output of get_history is [{"role": "user", "content": [{"type": "text", "text": "..."}]}]
		has_content = False
		for m in messages:
			for c in m["content"]:
				if c["type"] == "text" and "Bold interaction" in c["text"]:
					has_content = True
					break
		
		self.assertTrue(has_content)
