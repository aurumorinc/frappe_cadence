import frappe
from frappe.tests import IntegrationTestCase, UnitTestCase
from unittest.mock import patch, MagicMock

class TestSiftUtils(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Setup Sift Settings
        settings = frappe.get_doc({
            "doctype": "Sift Settings",
            "sift_base_url": "https://api.sift.example.com",
            "sift_api_key": "test_api_key"
        })
        # Try to insert, ignore if exists (though single doctypes don't insert the same way)
        try:
            settings.insert(ignore_if_duplicate=True)
        except Exception:
            pass
        frappe.db.set_single_value("Sift Settings", "sift_base_url", "https://api.sift.example.com")
        frappe.db.set_single_value("Sift Settings", "sift_api_key", "test_api_key")

        # Setup Email Template
        cls.template = frappe.get_doc({
            "doctype": "Email Template",
            "name": "Test Sift Template",
            "subject": "Test",
            "system_prompt": "You are a helpful assistant",
            "user_prompt": "Write an email",
            "status": "Enabled"
        }).insert(ignore_if_duplicate=True)

        # Setup Annotation
        cls.annotation = frappe.get_doc({
            "doctype": "Annotation",
            "parent": cls.template.name,
            "parenttype": "Email Template",
            "parentfield": "annotations",
            "reference_doctype": "CRM Lead",
            "reference_name": "L-001",
            "input": "test input",
            "output": ""
        }).insert(ignore_if_duplicate=True, ignore_links=True)
        
        # Add a complete annotation for optimization few-shot example
        cls.annotation2 = frappe.get_doc({
            "doctype": "Annotation",
            "parent": cls.template.name,
            "parenttype": "Email Template",
            "parentfield": "annotations",
            "reference_doctype": "CRM Lead",
            "reference_name": "L-002",
            "input": "test input 2",
            "output": "test output 2"
        }).insert(ignore_if_duplicate=True, ignore_links=True)

        cls.template.reload()

    @classmethod
    def tearDownClass(cls):
        frappe.db.rollback()
        super().tearDownClass()

    @patch("frappe_cadence.utils.sift.get_history")
    @patch("frappe_cadence.utils.sift.requests.post")
    def test_optimize(self, mock_post, mock_get_history):
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response
        
        mock_get_history.return_value = [{"role": "user", "content": [{"type": "text", "text": "test history"}]}]
        
        from frappe_cadence.utils.sift import optimize
        
        optimize("Email Template", self.template.name)
        
        self.template.reload()
        self.assertEqual(self.template.status, "Optimizing")
        
        # Verify payload structure
        self.assertTrue(mock_post.called)
        call_args = mock_post.call_args
        url = call_args[0][0]
        self.assertEqual(url, "https://api.sift.example.com/agents")
        
        payload = call_args[1].get("json")
        self.assertEqual(payload.get("agent_name"), f"agent-{self.template.name}")
        self.assertIn("optimize_callback", payload.get("webhook_url"))
        self.assertEqual(payload.get("metadata").get("template_name"), self.template.name)
        
        train_data = payload.get("dspy_params").get("state").get("default").get("train")
        self.assertEqual(len(train_data), 1)
        
        training_example = train_data[0]
        self.assertEqual(training_example.get("trace_id"), self.annotation2.name)
        self.assertEqual(training_example.get("feedback"), "test output 2")
        
        messages = training_example.get("messages")
        self.assertEqual(len(messages), 3)
        self.assertEqual(messages[0].get("role"), "system")
        self.assertEqual(messages[0].get("content"), "You are a helpful assistant")
        self.assertEqual(messages[1].get("role"), "user")
        self.assertEqual(messages[1].get("content")[0].get("text"), "test history")
        self.assertEqual(messages[2].get("role"), "user")
        self.assertEqual(messages[2].get("content")[0].get("text"), "test input 2")

    def test_optimize_callback(self):
        from frappe_cadence.utils.sift import optimize_callback
        
        kwargs = {
            "metadata": {
                "template_doctype": "Email Template",
                "template_name": self.template.name
            },
            "agent_name": "sift-agent-123"
        }
        
        result = optimize_callback(**kwargs)
        
        self.assertEqual(result.get("status"), "success")
        self.template.reload()
        self.assertEqual(self.template.sift_id, "sift-agent-123")
        self.assertEqual(self.template.status, "Disabled")

    @patch("frappe_cadence.utils.sift.get_history")
    @patch("frappe_cadence.utils.sift.requests.post")
    def test_predict(self, mock_post, mock_get_history):
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response
        
        mock_get_history.return_value = [{"role": "user", "content": [{"type": "text", "text": "test history predict"}]}]
        
        # Ensure we have a sift_id
        self.template.db_set("sift_id", "sift-agent-123")
        
        from frappe_cadence.utils.sift import predict
        
        predict("Email Template", self.template.name)
        
        self.template.reload()
        self.assertEqual(self.template.status, "Predicting")
        
        # One annotation is missing output, so one call should be made
        self.assertEqual(mock_post.call_count, 1)
        call_args = mock_post.call_args
        url = call_args[0][0]
        self.assertEqual(url, "https://api.sift.example.com/responses")
        
        payload = call_args[1].get("json")
        self.assertEqual(payload.get("model"), "sift-agent-123")
        self.assertIn("predict_callback", payload.get("webhook_url"))
        self.assertEqual(payload.get("metadata").get("annotation_id"), self.annotation.name)
        
        messages = payload.get("input")
        self.assertEqual(len(messages), 3)
        self.assertEqual(messages[0].get("role"), "system")
        self.assertEqual(messages[0].get("content"), "You are a helpful assistant")
        self.assertEqual(messages[1].get("role"), "user")
        self.assertEqual(messages[1].get("content")[0].get("text"), "test history predict")
        self.assertEqual(messages[2].get("role"), "user")
        self.assertEqual(messages[2].get("content")[0].get("text"), "test input")

    def test_predict_callback(self):
        from frappe_cadence.utils.sift import predict_callback
        
        kwargs = {
            "metadata": {
                "annotation_id": self.annotation.name
            },
            "output_text": "generated predicted output"
        }
        
        result = predict_callback(**kwargs)
        self.assertEqual(result.get("status"), "success")
        
        self.annotation.reload()
        self.assertEqual(self.annotation.output, "generated predicted output")
