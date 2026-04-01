import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_to_date, now_datetime
from unittest.mock import patch
from frappe_campaign.utils.agent import queue_generation_task

class TestAgentUtils(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.campaign_name = "TEST-EMAIL-CAMPAIGN-0001"
		cls.schedule_idx = 1
		cls.request_desc = f"Generate Prompt for {cls.campaign_name} - Step {cls.schedule_idx}"

		if not frappe.db.exists("Email Campaign", cls.campaign_name):
			doc = frappe.get_doc({
				"doctype": "Email Campaign",
				"campaign_name": "Test Campaign",
				"email_campaign_for": "CRM Lead",
				"recipient": "test@example.com",
				"name": cls.campaign_name,
				"status": "Draft"
			})
			doc.db_insert()

	@classmethod
	def tearDownClass(cls):
		frappe.db.rollback()
		super().tearDownClass()

	def tearDown(self):
		# Clean up integration requests
		frappe.db.delete("Integration Request", {
			"reference_doctype": "Email Campaign",
			"reference_docname": self.campaign_name
		})

	def setUp(self):
		frappe.db.delete("Integration Request", {
			"reference_doctype": "Email Campaign",
			"reference_docname": self.campaign_name
		})

	@patch("frappe_campaign.utils.agent.get_campaign_payload")
	@patch("frappe_campaign.utils.agent.frappe.enqueue")
	def test_queue_generation_task_new(self, mock_enqueue, mock_get_payload):
		mock_get_payload.return_value = {"test": "data"}

		# Should create a new Integration Request
		queue_generation_task(self.campaign_name, self.schedule_idx)

		requests = frappe.get_all("Integration Request", filters={
			"reference_docname": self.campaign_name,
			"status": "Queued"
		})
		self.assertEqual(len(requests), 1)
		mock_enqueue.assert_called_once()
		mock_get_payload.assert_called_once()

	@patch("frappe_campaign.utils.agent.get_campaign_payload")
	@patch("frappe_campaign.utils.agent.frappe.enqueue")
	def test_queue_generation_task_deduplicate_queued(self, mock_enqueue, mock_get_payload):
		mock_get_payload.return_value = {"test": "data"}

		# Create an existing Queued request
		frappe.get_doc({
			"doctype": "Integration Request",
			"integration_request_service": "AI Agent",
			"request_description": self.request_desc,
			"reference_doctype": "Email Campaign",
			"reference_docname": self.campaign_name,
			"status": "Queued",
			"data": "{}"
		}).insert(ignore_permissions=True)

		# Call the task again
		queue_generation_task(self.campaign_name, self.schedule_idx)

		# Should NOT call payload getter or enqueue
		mock_get_payload.assert_not_called()
		mock_enqueue.assert_not_called()

		requests = frappe.get_all("Integration Request", filters={
			"reference_docname": self.campaign_name,
		}, fields=["name", "status"])
		self.assertEqual(len(requests), 1)
		self.assertEqual(requests[0].status, "Queued")

	@patch("frappe_campaign.utils.agent.get_campaign_payload")
	@patch("frappe_campaign.utils.agent.frappe.enqueue")
	def test_queue_generation_task_deduplicate_authorized_valid(self, mock_enqueue, mock_get_payload):
		mock_get_payload.return_value = {"test": "data"}

		# Create an existing Authorized request (within 360 mins)
		frappe.get_doc({
			"doctype": "Integration Request",
			"integration_request_service": "AI Agent",
			"request_description": self.request_desc,
			"reference_doctype": "Email Campaign",
			"reference_docname": self.campaign_name,
			"status": "Authorized",
			"data": "{}"
		}).insert(ignore_permissions=True)

		# Call the task again
		queue_generation_task(self.campaign_name, self.schedule_idx)

		# Should NOT call payload getter or enqueue
		mock_get_payload.assert_not_called()
		mock_enqueue.assert_not_called()

		requests = frappe.get_all("Integration Request", filters={
			"reference_docname": self.campaign_name,
		}, fields=["name", "status"])
		self.assertEqual(len(requests), 1)
		self.assertEqual(requests[0].status, "Authorized")

	@patch("frappe_campaign.utils.agent.get_campaign_payload")
	@patch("frappe_campaign.utils.agent.frappe.enqueue")
	def test_queue_generation_task_deduplicate_authorized_timeout(self, mock_enqueue, mock_get_payload):
		mock_get_payload.return_value = {"test": "data"}

		# Create an existing Authorized request
		doc = frappe.get_doc({
			"doctype": "Integration Request",
			"integration_request_service": "AI Agent",
			"request_description": self.request_desc,
			"reference_doctype": "Email Campaign",
			"reference_docname": self.campaign_name,
			"status": "Authorized",
			"data": "{}"
		}).insert(ignore_permissions=True)

		# Force the modified date to be older than 360 minutes
		old_time = add_to_date(now_datetime(), minutes=-400)
		frappe.db.set_value("Integration Request", doc.name, "modified", old_time, update_modified=False)

		# Call the task again
		queue_generation_task(self.campaign_name, self.schedule_idx)

		# Should mark old as Failed and create a new Queued one
		mock_get_payload.assert_called_once()
		mock_enqueue.assert_called_once()

		requests = frappe.get_all("Integration Request", filters={
			"reference_docname": self.campaign_name,
		}, fields=["name", "status"], order_by="creation asc")

		self.assertEqual(len(requests), 2)
		self.assertEqual(requests[0].status, "Failed")
		self.assertEqual(requests[1].status, "Queued")
