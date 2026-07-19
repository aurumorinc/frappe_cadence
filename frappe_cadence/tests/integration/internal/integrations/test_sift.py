import frappe
import json
from unittest.mock import patch, MagicMock
from frappe.tests import IntegrationTestCase
from frappe_cadence.integrations.sift import optimize, optimize_callback, predict_callback

class TestSiftIntegration(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        frappe.db.rollback()
        super().tearDownClass()

    @patch("frappe_cadence.integrations.sift.requests.post")
    def test_optimize_payload_formatting(self, mock_post):
        # 2. Create Sift Settings
        settings = frappe.get_single("Sift Settings")
        settings.sift_base_url = "https://api.sift.com"
        settings.sift_api_key = "test_key"
        settings.save(ignore_permissions=True)

        # 3. Create a Provider and Model
        provider = frappe.get_doc({
            "doctype": "Model Provider",
            "model_provider_name": "OpenAI"
        })
        provider.insert(ignore_permissions=True, ignore_if_duplicate=True)

        model = frappe.get_doc({
            "doctype": "Model",
            "model_name": "gpt-4",
            "provider": provider.name
        })
        model.insert(ignore_permissions=True, ignore_if_duplicate=True)

        # 4. Create an Email Template
        template = frappe.get_doc({
            "doctype": "Email Template",
            "name": "Sift Test Template",
            "email_template_code": "agent-sift-test-template",
            "title": "Sift Test Template",
            "subject": "Test Subject",
            "model": model.name,
            "status": "Enabled"
        })
        template.insert(ignore_permissions=True)

        # 5. Create History record with HTML
        lead = frappe.get_doc({
            "doctype": "CRM Lead",
            "lead_name": "Sift Lead",
            "first_name": "Sift",
            "email_id": "sift_lead@example.com"
        })
        lead.insert(ignore_permissions=True)

        history = frappe.get_doc({
            "doctype": "History",
            "reference_doctype": "CRM Lead",
            "reference_name": lead.name,
            "url": "http://test.com",
            "markdown": "<p>History <em>test</em></p>"
        })
        history.insert(ignore_permissions=True)

        # 6. Create Annotation with Sender
        annotation = frappe.get_doc({
            "doctype": "Email Template Annotation",
            "parent": template.name,
            "parentfield": "annotations",
            "parenttype": "Email Template",
            "reference_doctype": "CRM Lead",
            "reference_name": lead.name,
            "sender": "Administrator",
            "subject": "Expected Subject",
            "salutation": "Expected Salutation",
            "body": "Expected Body",
            "cta": "Expected CTA",
            "sign_off": "Expected Sign Off"
        })
        annotation.insert(ignore_permissions=True)

        # Reload template to get children
        template.reload()

        # 7. Trigger optimize
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        frappe.db.delete("User Bio", {"reference_user": "Administrator"})
        frappe.get_doc({
            "doctype": "User Bio",
            "reference_user": "Administrator",
            "is_default": 1,
            "enabled": 1,
            "content": "<p>This is a <strong>test</strong> bio.</p>"
        }).insert(ignore_permissions=True)

        original_get_value = frappe.db.get_value
        def get_value_side_effect(*args, **kwargs):
            dt = args[0] if args else kwargs.get("doctype")
            fieldname = kwargs.get("fieldname") or (args[2] if len(args) > 2 else None)
            if dt == "User" and fieldname and "full_name" in fieldname:
                return frappe._dict(name="Administrator", full_name="Sift Test")
            return original_get_value(*args, **kwargs)

        with patch.object(frappe.db, "get_value", side_effect=get_value_side_effect):
            optimize(template.doctype, template.name)

        # 8. Assertions
        mock_post.assert_called_once()
        payload = mock_post.call_args[1].get("json")
        if not payload and "data" in mock_post.call_args[1]:
            payload = json.loads(mock_post.call_args[1]["data"])
            
        train_data = payload["dspy_params"]["state"]["predict"]["train"]
        self.assertEqual(len(train_data), 1)
        
        trace = train_data[0]
        self.assertEqual(trace["response"]["body"], "Expected Body")
        
        messages = trace["messages"]
        self.assertEqual(len(messages), 2) # System, History
        
        # Check System prompt has sender name and bio
        system_content = messages[0]["content"]
        self.assertIn("Sender Name: Sift Test", system_content)
        self.assertIn("This is a **test** bio.", system_content) # Markdown converted
        
        # Check History has markdown
        history_content = messages[1]["content"]
        self.assertEqual(history_content[0]["text"].strip(), "History *test*") # Markdown converted

    def test_optimize_callback(self):
        template = frappe.get_doc({
            "doctype": "Email Template",
            "name": "Callback Test Template",
            "title": "Callback Test Template",
            "subject": "Test Subject",
            "status": "Enabled"
        })
        template.insert(ignore_permissions=True)
        template.db_set("status", "Optimizing")

        # Test completed event
        completed_payload = {
            "type": "agent.completed",
            "metadata": {
                "doctype": template.doctype,
                "name": template.name
            },
            "data": [{"agent_name": "test_agent_123"}]
        }
        res = optimize_callback(**completed_payload)
        self.assertEqual(res.get("status"), "success")
        
        template.reload()
        self.assertEqual(template.sift_id, "test_agent_123")
        self.assertEqual(template.status, "Disabled")

        # Test failed event
        failed_payload = {
            "type": "agent.failed",
            "metadata": {
                "doctype": template.doctype,
                "name": template.name
            },
            "error": "Optimization failed"
        }
        res = optimize_callback(**failed_payload)
        self.assertEqual(res.get("status"), "failed")
        
        template.reload()
        self.assertEqual(template.status, "Enabled")

    def test_predict_callback(self):
        template = frappe.get_doc({
            "doctype": "Email Template",
            "name": "Predict Callback Test Template",
            "title": "Predict Callback Test Template",
            "subject": "Test Subject",
            "status": "Enabled"
        })
        template.insert(ignore_permissions=True)
        template.db_set("status", "Predicting")

        lead = frappe.get_doc({
            "doctype": "CRM Lead",
            "lead_name": "Sift Predict Lead",
            "first_name": "Sift",
        })
        lead.insert(ignore_permissions=True)

        annotation = frappe.get_doc({
            "doctype": "Email Template Annotation",
            "parent": template.name,
            "parentfield": "annotations",
            "parenttype": "Email Template",
            "reference_doctype": "CRM Lead",
            "reference_name": lead.name,
        })
        annotation.insert(ignore_permissions=True)

        # Test started event
        started_payload = {
            "type": "response.started",
            "metadata": {
                "name": annotation.name,
                "doctype": annotation.doctype
            }
        }
        res = predict_callback(**started_payload)
        self.assertEqual(res.get("status"), "ignored")

        # Test completed event
        completed_payload = {
            "type": "response.completed",
            "metadata": {
                "name": annotation.name,
                "doctype": annotation.doctype
            },
            "data": [
                    {
                        "content": [
                            {
                                "type": "output_text",
                                "text": '{"subject": "Predicted Subject", "body": "Predicted Body"}'
                            }
                        ]
                    }
                ]
        }
        res = predict_callback(**completed_payload)
        self.assertEqual(res.get("status"), "success")
        
        annotation.reload()
        self.assertEqual(annotation.subject, "Predicted Subject")
        self.assertEqual(annotation.body, "Predicted Body")

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
        try:
            settings.insert(ignore_if_duplicate=True)
        except Exception:
            pass
        frappe.db.set_single_value("Sift Settings", "sift_base_url", "https://api.sift.example.com")
        frappe.db.set_single_value("Sift Settings", "sift_api_key", "test_api_key")

        # Setup Model
        cls.model_provider = frappe.get_doc({
            "doctype": "Model Provider",
            "model_provider_name": "TestProvider"
        })
        try:
            cls.model_provider.insert(ignore_if_duplicate=True)
        except Exception:
            pass
            
        cls.model = frappe.get_doc({
            "doctype": "Model",
            "model_name": "test-model-4o",
            "provider": "TestProvider"
        })
        try:
            cls.model.insert(ignore_if_duplicate=True)
        except Exception:
            pass

        # Setup Email Template
        cls.template = frappe.get_doc({
            "doctype": "Email Template",
            "name": "Test Sift Template",
            "email_template_code": "agent-test-sift-template",
            "subject": "Test",
            "status": "Enabled",
            "model": "test-model-4o"
        }).insert(ignore_if_duplicate=True)

        # Setup Annotation (Email - missing output fields)
        cls.annotation = frappe.get_doc({
            "doctype": "Email Template Annotation",
            "parent": cls.template.name,
            "parenttype": "Email Template",
            "parentfield": "annotations",
            "reference_doctype": "CRM Lead",
            "reference_name": "L-001",
            "subject": "",
            "salutation": "",
            "body": "",
            "cta": "",
            "sign_off": ""
        }).insert(ignore_if_duplicate=True, ignore_links=True)
        
        # Add a complete annotation for optimization few-shot example (Email)
        cls.annotation2 = frappe.get_doc({
            "doctype": "Email Template Annotation",
            "parent": cls.template.name,
            "parenttype": "Email Template",
            "parentfield": "annotations",
            "reference_doctype": "CRM Lead",
            "reference_name": "L-002",
            "subject": "test subject 2",
            "salutation": "test salutation 2",
            "body": "test body 2",
            "cta": "test cta 2",
            "sign_off": "test sign_off 2",
            "feedback": "good job"
        }).insert(ignore_if_duplicate=True, ignore_links=True)

        # Setup Whatsapp Template
        cls.whatsapp_template = frappe.get_doc({
            "doctype": "WhatsApp Template",
            "name": "Test Whatsapp Template",
            "title": "Test Whatsapp Template",
            "status": "Enabled",
            "model": "test-model-4o"
        }).insert(ignore_if_duplicate=True)

        # Setup Annotation (Whatsapp - single field)
        cls.whatsapp_annotation = frappe.get_doc({
            "doctype": "Whatsapp Template Annotation",
            "parent": cls.whatsapp_template.name,
            "parenttype": "WhatsApp Template",
            "parentfield": "annotations",
            "reference_doctype": "CRM Lead",
            "reference_name": "L-003",
            "output": "whatsapp test output"
        }).insert(ignore_if_duplicate=True, ignore_links=True)

        
        cls.template.reload()
        cls.whatsapp_template.reload()

    @classmethod
    def tearDownClass(cls):
        frappe.db.rollback()
        super().tearDownClass()

    def test_schema_generation(self):
        from frappe_cadence.integrations.sift import get_annotation_schema, get_annotation_response, is_annotation_pending
        
        # Email Schema
        email_schema = get_annotation_schema("Email Template Annotation")
        self.assertEqual(email_schema["name"], "EmailTemplateAnnotation")
        self.assertIn("subject", email_schema["schema"]["properties"])
        self.assertIn("body", email_schema["schema"]["properties"])
        self.assertIn("sign_off", email_schema["schema"]["properties"])
        
        # WhatsApp Schema should just be standard since we don't pass schema for single output, but test it anyway
        wa_schema = get_annotation_schema("Whatsapp Template Annotation")
        self.assertIn("output", wa_schema["schema"]["properties"])
        
        # Test get_annotation_response
        self.annotation2.reload()
        resp = get_annotation_response(self.annotation2)
        self.assertIsInstance(resp, dict)
        self.assertEqual(resp["subject"], "test subject 2")
        self.assertEqual(resp["body"], "test body 2")
        
        self.whatsapp_annotation.reload()
        # Reset to original just in case other tests modified it
        self.whatsapp_annotation.db_set("output", "whatsapp test output")
        wa_resp = get_annotation_response(self.whatsapp_annotation)
        self.assertIsInstance(wa_resp, str)
        self.assertEqual(wa_resp, "whatsapp test output")
        
        # Test pending
        self.assertTrue(is_annotation_pending(self.annotation))
        self.assertFalse(is_annotation_pending(self.annotation2))
        self.assertFalse(is_annotation_pending(self.whatsapp_annotation))

    @patch("frappe_cadence.cadence.doctype.history.history.get_history")
    @patch("frappe_cadence.integrations.sift.requests.post")
    def test_optimize(self, mock_post, mock_get_history):
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response
        
        mock_get_history.return_value = [{"role": "user", "content": [{"type": "text", "text": "test history"}]}]
        
        frappe.db.delete("User Bio", {"reference_user": "test_sender@example.com"})
        frappe.get_doc({
            "doctype": "User Bio",
            "reference_user": "test_sender@example.com",
            "is_default": 1,
            "enabled": 1,
            "content": "<b>Bold Bio</b>"
        }).insert(ignore_permissions=True, ignore_links=True)

        original_get_value = frappe.db.get_value
        def get_value_side_effect(*args, **kwargs):
            dt = args[0] if args else kwargs.get("doctype")
            fieldname = kwargs.get("fieldname") or (args[2] if len(args) > 2 else None)
            if dt == "User" and fieldname and "full_name" in fieldname:
                return frappe._dict(name="test_sender@example.com", full_name="Test Sender")
            return original_get_value(*args, **kwargs)
            
        with patch.object(frappe.db, "get_value") as mock_get_value:
            mock_get_value.side_effect = get_value_side_effect
            
            from frappe_cadence.integrations.sift import optimize
            
            self.template.reload()
            for ann in self.template.get("annotations"):
                frappe.db.set_value("Email Template Annotation", ann.name, "sender", "test_sender@example.com")
            
            original_get_doc = frappe.get_doc
            def get_doc_mock(*args, **kwargs):
                doc = original_get_doc(*args, **kwargs)
                if doc.doctype == "Email Template":
                    doc.email_template_code = "agent-test-sift-template"
                return doc
                
            with patch("frappe_cadence.integrations.sift.frappe.get_doc", side_effect=get_doc_mock):
                optimize("Email Template", self.template.name)
        
        self.template.reload()
        self.assertEqual(self.template.status, "Optimizing")
        
        # Verify payload structure
        self.assertTrue(mock_post.called)
        call_args = mock_post.call_args
        url = call_args[0][0]
        self.assertEqual(url, "https://api.sift.example.com/agents")
        
        payload = call_args[1].get("json")
        self.assertEqual(payload.get("agent_name"), "agent-test-sift-template")
        self.assertIn("optimize_callback", payload.get("webhook").get("url"))
        self.assertEqual(payload.get("webhook").get("metadata").get("name"), self.template.name)
        self.assertEqual(payload.get("webhook").get("metadata").get("doctype"), "Email Template")
        
        self.assertEqual(payload.get("litellm_params").get("model"), "testprovider/test-model-4o")
        
        train_data = payload.get("dspy_params").get("state").get("predict").get("train")
        self.assertEqual(len(train_data), 1)
        
        training_example = train_data[0]
        self.assertEqual(training_example.get("trace_id"), self.annotation2.name)
        self.assertEqual(training_example.get("feedback"), "good job")
        self.assertEqual(training_example.get("response").get("subject"), "test subject 2")
        
        messages = training_example.get("messages")
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0].get("role"), "system")
        self.assertIn("Test Sender", messages[0].get("content"))
        self.assertIn("**Bold Bio**", messages[0].get("content"))
        
        self.assertEqual(messages[1].get("role"), "user")
        self.assertEqual(messages[1].get("content")[0].get("text"), "test history")

    def test_optimize_callback(self):
        from frappe_cadence.integrations.sift import optimize_callback
        
        kwargs = {
            "type": "agent.completed",
            "metadata": {
                "doctype": "Email Template",
                "name": self.template.name
            },
            "data": [{"agent_name": "sift-agent-123"}]
        }
        
        result = optimize_callback(**kwargs)
        
        self.assertEqual(result.get("status"), "success")
        self.template.reload()
        self.assertEqual(self.template.sift_id, "sift-agent-123")
        self.assertEqual(self.template.status, "Disabled")

    @patch("frappe_cadence.cadence.doctype.history.history.get_history")
    @patch("frappe_cadence.integrations.sift.requests.post")
    def test_predict(self, mock_post, mock_get_history):
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response
        
        mock_get_history.return_value = [{"role": "user", "content": [{"type": "text", "text": "test history predict"}]}]
        
        # Ensure we have a sift_id
        self.template.db_set("sift_id", "sift-agent-123")
        
        frappe.db.delete("User Bio", {"reference_user": "test_sender@example.com"})
        frappe.get_doc({
            "doctype": "User Bio",
            "reference_user": "test_sender@example.com",
            "is_default": 1,
            "enabled": 1,
            "content": "<b>Bold Bio</b>"
        }).insert(ignore_permissions=True, ignore_links=True)

        original_get_value = frappe.db.get_value
        def get_value_side_effect(*args, **kwargs):
            dt = args[0] if args else kwargs.get("doctype")
            fieldname = kwargs.get("fieldname") or (args[2] if len(args) > 2 else None)
            if dt == "User" and fieldname and "full_name" in fieldname:
                return frappe._dict(name="test_sender@example.com", full_name="Test Sender")
            return original_get_value(*args, **kwargs)
            
        with patch.object(frappe.db, "get_value") as mock_get_value:
            mock_get_value.side_effect = get_value_side_effect
            
            from frappe_cadence.integrations.sift import predict
            
            self.template.reload()
            for ann in self.template.get("annotations"):
                frappe.db.set_value("Email Template Annotation", ann.name, "sender", "test_sender@example.com")
                
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
        self.assertTrue(payload.get("background"))
        self.assertIn("predict_callback", payload.get("webhook").get("url"))
        self.assertEqual(payload.get("webhook").get("metadata").get("name"), self.annotation.name)
        self.assertEqual(payload.get("webhook").get("metadata").get("doctype"), "Email Template Annotation")
        
        self.assertIn("response_format", payload)
        self.assertEqual(payload.get("response_format").get("type"), "json_schema")
        self.assertEqual(payload.get("response_format").get("json_schema").get("name"), "EmailTemplateAnnotation")
        
        messages = payload.get("input")
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0].get("role"), "system")
        self.assertIn("Test Sender", messages[0].get("content"))
        self.assertIn("**Bold Bio**", messages[0].get("content"))

        self.assertEqual(messages[1].get("role"), "user")
        self.assertEqual(messages[1].get("content")[0].get("text"), "test history predict")

    def test_predict_callback_structured(self):
        from frappe_cadence.integrations.sift import predict_callback
        import json
        
        structured_output = {
            "subject": "predicted subject",
            "body": "predicted body"
        }
        
        kwargs = {
            "type": "response.completed",
            "metadata": {
                "name": self.annotation.name,
                "doctype": "Email Template Annotation"
            },
            "data": [{"content": [{"text": json.dumps(structured_output)}]}]
        }
        
        result = predict_callback(**kwargs)
        self.assertEqual(result.get("status"), "success")
        
        self.annotation.reload()
        self.assertEqual(self.annotation.subject, "predicted subject")
        self.assertEqual(self.annotation.body, "predicted body")

    def test_predict_callback_unstructured(self):
        from frappe_cadence.integrations.sift import predict_callback
        
        kwargs = {
            "type": "response.completed",
            "metadata": {
                "name": self.whatsapp_annotation.name,
                "doctype": "Whatsapp Template Annotation"
            },
            "data": [{"content": [{"text": "new unstructured output"}]}]
        }
        
        result = predict_callback(**kwargs)
        self.assertEqual(result.get("status"), "success")
        
        self.whatsapp_annotation.reload()
        self.assertEqual(self.whatsapp_annotation.output, "new unstructured output")
