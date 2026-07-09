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

        if not frappe.db.exists("User", "test_sender@example.com"):
            frappe.get_doc({
                "doctype": "User",
                "email": "test_sender@example.com",
                "first_name": "Test",
                "last_name": "Sender",
                "bio": "<b>Bold Bio</b>"
            }).insert(ignore_permissions=True)

        # Setup Email Template
        frappe.db.delete("Email Template", {"name": "Test Sift Template"})
        cls.template = frappe.get_doc({
            "doctype": "Email Template",
            "name": "Test Sift Template",
            "subject": "Test",
            "system_prompt": "You are a helpful assistant",
            "user_prompt": "Write an email",
            "status": "Enabled"
        }).insert(ignore_permissions=True)

        # Clean up old annotations
        frappe.db.delete("Annotation", {"parent": cls.template.name})

        # Setup Annotation
        cls.annotation = frappe.get_doc({
            "doctype": "Annotation",
            "parent": cls.template.name,
            "parenttype": "Email Template",
            "parentfield": "annotations",
            "reference_doctype": "CRM Lead",
            "reference_name": "L-001",
            "sender": "test_sender@example.com",
            "output": ""
        }).insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        
        # Add a complete annotation for optimization few-shot example
        cls.annotation2 = frappe.get_doc({
            "doctype": "Annotation",
            "parent": cls.template.name,
            "parenttype": "Email Template",
            "parentfield": "annotations",
            "reference_doctype": "CRM Lead",
            "reference_name": "L-002",
            "sender": "test_sender@example.com",
            "output": "test output 2"
        }).insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        
        # Setup History
        frappe.get_doc({
            "doctype": "History",
            "reference_doctype": "CRM Lead",
            "reference_name": "L-002",
            "content": "<h1>Previous</h1>",
            "url": "http://example.com/test",
            "type": "Note"
        }).insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)

        cls.template.reload()
        frappe.db.commit()

    @classmethod
    def tearDownClass(cls):
        frappe.db.rollback()
        
        # Cleanup
        frappe.db.delete("Email Template", {"name": "Test Sift Template"})
        frappe.db.delete("Annotation", {"reference_doctype": "CRM Lead", "reference_name": ["in", ["L-001", "L-002"]]})
        frappe.db.delete("History", {"reference_doctype": "CRM Lead", "reference_name": "L-002"})
        frappe.db.delete("User", {"email": "test_sender@example.com"})
        frappe.db.commit()
        
        super().tearDownClass()

    @patch("frappe_cadence.utils.sift.requests.post")
    def test_optimize(self, mock_post):
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response
        
        original_get_value = frappe.db.get_value
        def get_value_side_effect(*args, **kwargs):
            dt = args[0] if args else kwargs.get("doctype")
            if dt == "User":
                return {"full_name": "Test Sender", "bio": "<b>Bold Bio</b>"}
            return original_get_value(*args, **kwargs)
            
        with patch.object(frappe.db, "get_value") as mock_get_value:
            mock_get_value.side_effect = get_value_side_effect
            
            from frappe_cadence.utils.sift import optimize
            
            self.template.reload()
            for ann in self.template.get("annotations"):
                frappe.db.set_value("Annotation", ann.name, "sender", "test_sender@example.com")
            
            optimize("Email Template", self.template.name)
            
            self.template.reload()
            self.assertEqual(self.template.status, "Optimizing")
            
            # Verify payload structure
            self.assertTrue(mock_post.called)
            call_args = mock_post.call_args
            url = call_args[0][0]
            self.assertEqual(url, "https://api.sift.example.com/agents")
            
            payload = call_args[1].get("json")
            self.assertEqual(payload.get("system_prompt"), "You are a helpful assistant")
            self.assertEqual(payload.get("user_prompt"), "Write an email")
            self.assertEqual(len(payload.get("few_shot_examples")), 1)
            
            few_shot = payload.get("few_shot_examples")[0]
            print("FEW_SHOT:", few_shot)
            self.assertEqual(few_shot.get("output"), "test output 2")
            self.assertEqual(few_shot.get("input"), "Write an email")
            self.assertEqual(few_shot.get("senders_name"), "Test Sender")
            self.assertEqual(few_shot.get("senders_bio"), "**Bold Bio**")
            self.assertEqual(few_shot.get("history").strip(), "Previous\n========") # History markdown
            
            self.assertIn("optimize_callback", payload.get("webhook_url"))
            self.assertEqual(payload.get("metadata").get("template_name"), self.template.name)

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

    @patch("frappe_cadence.utils.sift.requests.post")
    def test_predict(self, mock_post):
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response
        
        original_get_value = frappe.db.get_value
        def get_value_side_effect(*args, **kwargs):
            dt = args[0] if args else kwargs.get("doctype")
            if dt == "User":
                return {"full_name": "Test Sender", "bio": "<b>Bold Bio</b>"}
            return original_get_value(*args, **kwargs)
            
        with patch.object(frappe.db, "get_value") as mock_get_value:
            mock_get_value.side_effect = get_value_side_effect
            
            # Ensure we have a sift_id
            self.template.db_set("sift_id", "sift-agent-123")
            
            from frappe_cadence.utils.sift import predict
            
            self.template.reload()
            for ann in self.template.get("annotations"):
                frappe.db.set_value("Annotation", ann.name, "sender", "test_sender@example.com")
            
            predict("Email Template", self.template.name)
            
            self.template.reload()
            self.assertEqual(self.template.status, "Predicting")
            
            # One annotation is missing output, so one call should be made
            self.assertEqual(mock_post.call_count, 1)
            call_args = mock_post.call_args
            url = call_args[0][0]
            self.assertEqual(url, "https://api.sift.example.com/responses")
            
            payload = call_args[1].get("json")
            self.assertEqual(payload.get("agent_name"), "sift-agent-123")
            self.assertEqual(payload.get("input"), "Write an email")
            self.assertEqual(payload.get("senders_name"), "Test Sender")
            self.assertEqual(payload.get("senders_bio"), "**Bold Bio**")
            
            self.assertIn("predict_callback", payload.get("webhook_url"))
            self.assertEqual(payload.get("metadata").get("annotation_id"), self.annotation.name)

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
