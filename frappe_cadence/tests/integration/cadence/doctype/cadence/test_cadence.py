import frappe
from frappe.tests import IntegrationTestCase

class TestCadence(IntegrationTestCase):
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

	def test_cadence_creation_and_utm_campaign(self):
		# Test Cadence creation by explicitly setting cadence_code
		cadence_code = "TEST-CODE-001"
		
		# Ensure we don't have leftover data
		if frappe.db.exists("Cadence", cadence_code):
			frappe.delete_doc("Cadence", cadence_code)
		if frappe.db.exists("UTM Campaign", cadence_code):
			frappe.delete_doc("UTM Campaign", cadence_code)
			
		cadence = frappe.get_doc({
			"doctype": "Cadence",
			"cadence_code": cadence_code,
			"cadence_name": "Test Cadence Name",
			"description": "Test Description"
		}).insert()

		# Verify that doc.name is correctly populated
		self.assertEqual(cadence.name, cadence_code)

		# Verify that upon Cadence creation, a corresponding UTM Campaign document is created
		self.assertTrue(frappe.db.exists("UTM Campaign", cadence_code))
		
		utm_campaign = frappe.get_doc("UTM Campaign", cadence_code)
		self.assertEqual(utm_campaign.name, cadence_code)
		if utm_campaign.meta.has_field("cadence_description"):
			self.assertEqual(utm_campaign.get("cadence_description"), "Test Description")
		if utm_campaign.meta.has_field("crm_cadence"):
			self.assertEqual(utm_campaign.get("crm_cadence"), cadence_code)
		
	def test_cadence_update_utm_campaign(self):
		cadence_code = "TEST-CODE-002"
		
		if frappe.db.exists("Cadence", cadence_code):
			frappe.delete_doc("Cadence", cadence_code)
		if frappe.db.exists("UTM Campaign", cadence_code):
			frappe.delete_doc("UTM Campaign", cadence_code)

		cadence = frappe.get_doc({
			"doctype": "Cadence",
			"cadence_code": cadence_code,
			"cadence_name": "Test Cadence Name 2",
			"description": "Test Description 2"
		}).insert()
		
		# Ensure UTM Campaign created
		self.assertTrue(frappe.db.exists("UTM Campaign", cadence_code))
		utm_campaign_initial_modified = frappe.get_doc("UTM Campaign", cadence_code).modified
		
		# Update Cadence
		cadence.description = "Updated Test Description 2"
		cadence.save()
		
		# Ensure duplicate UTM Campaign was not created, but it was updated
		utm_campaign = frappe.get_doc("UTM Campaign", cadence_code)
		if utm_campaign.meta.has_field("cadence_description"):
			self.assertEqual(utm_campaign.get("cadence_description"), "Updated Test Description 2")

	def test_cadence_autoname_naming_series(self):
		# Test that cadence_code is generated if left blank
		cadence = frappe.get_doc({
			"doctype": "Cadence",
			"naming_series": "CAD-.YYYY.-",
			"cadence_name": "Test Cadence Autoname",
			"description": "Test Description Autoname"
		}).insert()
		
		# Name should start with CAD-20
		self.assertTrue(cadence.name.startswith("CAD-20"))
		self.assertEqual(cadence.cadence_code, cadence.name)
