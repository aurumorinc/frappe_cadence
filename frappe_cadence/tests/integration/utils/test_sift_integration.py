import frappe
import json
from unittest.mock import patch, MagicMock
from frappe.tests import IntegrationTestCase
from frappe_cadence.utils.sift import optimize

class TestSiftIntegration(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        frappe.db.rollback()
        super().tearDownClass()

    @patch("frappe_cadence.utils.sift.requests.post")
    def test_optimize_payload_formatting(self, mock_post):
        # 1. Create a User with an HTML bio
        user = frappe.get_doc({
            "doctype": "User",
            "email": "sift_test_user@example.com",
            "first_name": "Sift",
            "last_name": "Test",
            "bio": "<p>This is a <strong>test</strong> bio.</p>"
        })
        user.insert(ignore_permissions=True, ignore_if_duplicate=True)

        # 2. Create Sift Settings
        settings = frappe.get_single("Sift Settings")
        settings.sift_base_url = "https://api.sift.com"
        settings.sift_api_key = "test_key"
        settings.save(ignore_permissions=True)

        # 3. Create a Model
        model = frappe.get_doc({
            "doctype": "Model",
            "model_name": "gpt-4",
            "provider": "OpenAI"
        })
        model.insert(ignore_permissions=True, ignore_if_duplicate=True)

        # 4. Create an Email Template
        template = frappe.get_doc({
            "doctype": "Email Template",
            "title": "Sift Test Template",
            "subject": "Test Subject",
            "system_prompt": "System Prompt Content",
            "user_prompt": "User Prompt Content",
            "model": model.name,
            "status": "Enabled"
        })
        template.insert(ignore_permissions=True)

        # 5. Create History record with HTML
        lead = frappe.get_doc({
            "doctype": "CRM Lead",
            "lead_name": "Sift Lead",
            "email_id": "sift_lead@example.com"
        })
        lead.insert(ignore_permissions=True)

        history = frappe.get_doc({
            "doctype": "History",
            "reference_doctype": "CRM Lead",
            "reference_name": lead.name,
            "content": "<p>History <em>test</em></p>"
        })
        history.insert(ignore_permissions=True)

        # 6. Create Annotation with Sender
        annotation = frappe.get_doc({
            "doctype": "Annotation",
            "parent": template.name,
            "parentfield": "annotations",
            "parenttype": "Email Template",
            "reference_doctype": "CRM Lead",
            "reference_name": lead.name,
            "sender": user.name,
            "output": "Expected Output"
        })
        annotation.insert(ignore_permissions=True)

        # Reload template to get children
        template.reload()

        # 7. Trigger optimize
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        optimize(template.doctype, template.name)

        # 8. Assertions
        mock_post.assert_called_once()
        payload = mock_post.call_args[1].get("json")
        if not payload and "data" in mock_post.call_args[1]:
            payload = json.loads(mock_post.call_args[1]["data"])
            
        train_data = payload["dspy_params"]["state"]["default"]["train"]
        self.assertEqual(len(train_data), 1)
        
        trace = train_data[0]
        self.assertEqual(trace["feedback"], "Expected Output")
        
        messages = trace["messages"]
        self.assertEqual(len(messages), 3) # System, History, User
        
        # Check System prompt has sender name and bio
        system_content = messages[0]["content"]
        self.assertIn("System Prompt Content", system_content)
        self.assertIn("Sender Name: Sift Test", system_content)
        self.assertIn("This is a **test** bio.", system_content) # Markdown converted
        
        # Check History has markdown
        history_content = messages[1]["content"]
        self.assertEqual(history_content[0]["text"].strip(), "History *test*") # Markdown converted
        
        # Check User prompt
        user_content = messages[2]["content"]
        self.assertEqual(user_content[0]["text"], "User Prompt Content")

        # Cleanup
        template.delete()
        history.delete()
        lead.delete()
