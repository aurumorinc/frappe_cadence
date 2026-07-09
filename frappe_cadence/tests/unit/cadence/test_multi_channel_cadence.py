import unittest
from unittest.mock import patch, MagicMock
import frappe
from frappe.tests import UnitTestCase

class TestMultiChannelCadence(UnitTestCase):

    @patch("frappe_cadence.cadence.multi_channel_cadence.frappe.get_doc")
    @patch("frappe_cadence.cadence.multi_channel_cadence.frappe.get_all")
    @patch("frappe_cadence.cadence.multi_channel_cadence.emit_event")
    def test_process_cadence_step_communication_generation(self, mock_emit_event, mock_get_all, mock_get_doc):
        from frappe_cadence.cadence.multi_channel_cadence import process_cadence_step
        
        # Setup mocks
        # 1. First get_all checks for idempotency, return empty list to proceed
        mock_get_all.return_value = []
        
        # 2. Setup mock documents
        mock_schedule = MagicMock()
        mock_schedule.reference_doctype = "Email Template"
        mock_schedule.reference_name = "Template-001"
        
        mock_mcc = MagicMock()
        row = MagicMock()
        row.channel = "Email"
        row.reference_cadence_provider = "Apollo"
        mock_mcc.get.return_value = [row]
        
        mock_template = MagicMock()
        mock_template.status = "Enabled"
        mock_template.subject = "Test Subject"
        mock_template.message = "Test Message"
        mock_template.get.side_effect = lambda k, default=None: getattr(mock_template, k, default)
        
        mock_comm = MagicMock()
        
        original_get_doc = frappe.get_doc
        def get_doc_side_effect(*args, **kwargs):
            if len(args) == 2 and args[0] == "Cadence Multi Channel Schedule":
                return mock_schedule
            elif len(args) == 2 and args[0] == "Multi Channel Cadence":
                return mock_mcc
            elif len(args) == 2 and args[0] == "Email Template":
                return mock_template
            elif len(args) == 1 and isinstance(args[0], dict) and args[0].get("doctype") == "Communication":
                # Intercept Communication creation to verify kwargs
                for k, v in args[0].items():
                    setattr(mock_comm, k, v)
                return mock_comm
            return original_get_doc(*args, **kwargs)
            
        mock_get_doc.side_effect = get_doc_side_effect
        
        # Act
        process_cadence_step("MCC-001", "SCHED-001")
        
        # Assert
        self.assertEqual(mock_comm.doctype, "Communication")
        self.assertEqual(mock_comm.reference_cadence_provider, "Apollo")
        self.assertEqual(mock_comm.communication_medium, "Email")
        mock_comm.insert.assert_called_once_with(ignore_permissions=True)
        mock_emit_event.assert_called_once_with("cadence_step_completed", {"cadence_name": "MCC-001", "schedule_name": "SCHED-001"})

    @patch("frappe_cadence.cadence.multi_channel_cadence.requests.post")
    @patch("frappe_cadence.cadence.multi_channel_cadence.wait_for_event")
    @patch("frappe_cadence.cadence.multi_channel_cadence.frappe.get_all")
    @patch("frappe_cadence.cadence.multi_channel_cadence.get_url")
    @patch("frappe_cadence.cadence.multi_channel_cadence.add_months")
    def test_process_cadence_step_sift_integration(self, mock_add_months, mock_get_url, mock_get_all, mock_wait_for_event, mock_post):
        mock_get_url.return_value = "http://test.com/webhook"
        mock_add_months.return_value = "2024-01-01"
        from frappe_cadence.cadence.multi_channel_cadence import process_cadence_step
        import json
        
        # Setup Sift settings
        mock_sift_settings = MagicMock()
        mock_sift_settings.sift_base_url = "https://api.sift.com"
        mock_sift_settings.get_password.return_value = "sift_secret_key"

        # Setup mock documents
        mock_schedule = MagicMock()
        mock_schedule.reference_doctype = "Email Template"
        mock_schedule.reference_name = "Template-002"
        
        mock_mcc = MagicMock()
        mock_mcc.cadence_for = "CRM Lead"
        mock_mcc.recipient = "LEAD-001"
        mock_mcc.owner = "user@test.com"
        mock_mcc.sift_id = "agent-mcc"
        row = MagicMock()
        row.channel = "Email"
        row.reference_cadence_provider = "Apollo"
        mock_mcc.get.return_value = [row]
        
        mock_template = MagicMock()
        mock_template.status = "Prompt"
        mock_template.system_prompt = "You are an assistant"
        mock_template.user_prompt = "Write an email"
        
        mock_lead = MagicMock()
        mock_lead.name = "LEAD-001"
        mock_lead.organization = "ORG-001"
        
        mock_comm = MagicMock()
        mock_comm.name = "COMM-001"
        
        mock_history = MagicMock()
        mock_history.content = "Test History"
        mock_history.name = "HIST-001"
        
        mock_history_image = MagicMock()
        mock_history_image.image = "/files/test.png"
        
        mock_file = MagicMock()
        mock_file.presigned_url = "https://s3.example.com/test.png?sig=123"
        
        # Mock get_all
        def get_all_side_effect(doctype, *args, **kwargs):
            if doctype == "Communication":
                return []
            elif doctype == "History":
                filters = kwargs.get("filters", [])
                for f in filters:
                    if len(f) >= 3 and f[2] == "LEAD-001":
                        return [mock_history]
                return []
            elif doctype == "History Image":
                return [mock_history_image]
            return []
            
        mock_get_all.side_effect = get_all_side_effect
        
        original_get_doc = frappe.get_doc
        def get_doc_side_effect(*args, **kwargs):
            if len(args) == 2 and args[0] == "Cadence Multi Channel Schedule":
                return mock_schedule
            elif len(args) == 2 and args[0] == "Multi Channel Cadence":
                return mock_mcc
            elif len(args) == 2 and args[0] == "Email Template":
                return mock_template
            elif len(args) == 2 and args[0] == "CRM Lead":
                return mock_lead
            elif len(args) == 2 and args[0] == "File":
                return mock_file
            elif len(args) == 1 and isinstance(args[0], dict) and args[0].get("doctype") == "Communication":
                return mock_comm
            return original_get_doc(*args, **kwargs)
            
        original_get_single = frappe.get_single
        def get_single_side_effect(*args, **kwargs):
            if args[0] == "Sift Settings":
                return mock_sift_settings
            return original_get_single(*args, **kwargs)
            
        original_get_value = frappe.db.get_value
        def get_value_side_effect(*args, **kwargs):
            doctype = kwargs.get("doctype") or (args[0] if len(args) > 0 else None)
            filters = kwargs.get("filters") or (args[1] if len(args) > 1 else None)
            if doctype == "User" and filters == "user@test.com":
                return {"full_name": "Test User", "bio": "<p>I am a <strong>bold</strong> user.</p>"}
            return original_get_value(*args, **kwargs)
            
        with patch.object(frappe, "get_doc", side_effect=get_doc_side_effect):
            with patch.object(frappe, "get_single", side_effect=get_single_side_effect):
                with patch.object(frappe.db, "get_value", side_effect=get_value_side_effect):
                    with patch("frappe_cadence.cadence.multi_channel_cadence.frappe.cache") as mock_cache:
                        mock_cache.return_value.get_value.return_value = None
                        process_cadence_step("MCC-001", "SCHED-001")
                    
                    # Assert
                    mock_post.assert_called_once()
                    called_url = mock_post.call_args[0][0]
                    self.assertEqual(called_url, "https://api.sift.com/responses")
                    
                    headers = mock_post.call_args[1]["headers"]
                    self.assertEqual(headers["Authorization"], "Bearer sift_secret_key")
                    
                    data = json.loads(mock_post.call_args[1]["data"])
                    self.assertIn("webhook_url", data["metadata"])
                    self.assertEqual(data["metadata"]["webhook_url"], "http://test.com/webhook")
                    self.assertEqual(data["model"], "agent-mcc")
                    
                    # Verify input payload structure
                    input_data = data["input"]
                    self.assertEqual(len(input_data), 3) # System, History, User
                    
                    self.assertEqual(input_data[0]["role"], "system")
                    self.assertIn("You are an assistant", input_data[0]["content"])
                    
                    self.assertEqual(input_data[1]["role"], "user")
                    self.assertEqual(len(input_data[1]["content"]), 2) # text + image
                    self.assertEqual(input_data[1]["content"][0]["type"], "text")
                    self.assertEqual(input_data[1]["content"][0]["text"], "Test History")
                    self.assertEqual(input_data[1]["content"][1]["type"], "image_url")
                    self.assertEqual(input_data[1]["content"][1]["image_url"]["url"], "https://s3.example.com/test.png?sig=123")
                    
                    self.assertEqual(input_data[2]["role"], "user")
                    self.assertEqual(input_data[2]["content"][0]["type"], "text")
                    self.assertEqual(input_data[2]["content"][0]["text"], "Write an email")
                    
                    mock_wait_for_event.assert_called_once_with(
                        "callback",
                        condition="argument.get('communication_id') == 'COMM-001'"
                    )

    @patch("frappe_cadence.cadence.multi_channel_cadence.requests.post")
    @patch("frappe_cadence.cadence.multi_channel_cadence.wait_for_event")
    @patch("frappe_cadence.cadence.multi_channel_cadence.frappe.get_all")
    @patch("frappe_cadence.cadence.multi_channel_cadence.get_url")
    def test_process_cadence_step_sift_payload_markdown(self, mock_get_url, mock_get_all, mock_wait_for_event, mock_post):
        mock_get_url.return_value = "http://test.com/webhook"
        from frappe_cadence.cadence.multi_channel_cadence import process_cadence_step
        import json
        
        # Setup Sift settings
        mock_sift_settings = MagicMock()
        mock_sift_settings.sift_base_url = "https://api.sift.com"
        mock_sift_settings.get_password.return_value = "sift_secret_key"

        # Setup mock documents
        mock_schedule = MagicMock()
        mock_schedule.reference_doctype = "Email Template"
        mock_schedule.reference_name = "Template-003"
        
        mock_mcc = MagicMock()
        mock_mcc.cadence_for = "CRM Lead"
        mock_mcc.recipient = "LEAD-002"
        mock_mcc.owner = "user@test.com"
        mock_mcc.sift_id = "agent-mcc-2"
        row = MagicMock()
        row.channel = "Email"
        row.reference_cadence_provider = "Apollo"
        mock_mcc.get.return_value = [row]
        
        mock_template = MagicMock()
        mock_template.status = "Prompt"
        mock_template.system_prompt = "You are an assistant"
        mock_template.user_prompt = "Write an email"
        
        mock_lead = MagicMock()
        mock_lead.name = "LEAD-002"
        mock_lead.organization = None
        
        mock_comm = MagicMock()
        mock_comm.name = "COMM-002"
        
        # Mock get_all to return no drafts and no history
        def get_all_side_effect(doctype, *args, **kwargs):
            return []
            
        mock_get_all.side_effect = get_all_side_effect
        
        original_get_doc = frappe.get_doc
        def get_doc_side_effect(*args, **kwargs):
            if len(args) == 2 and args[0] == "Cadence Multi Channel Schedule":
                return mock_schedule
            elif len(args) == 2 and args[0] == "Multi Channel Cadence":
                return mock_mcc
            elif len(args) == 2 and args[0] == "Email Template":
                return mock_template
            elif len(args) == 2 and args[0] == "CRM Lead":
                return mock_lead
            elif len(args) == 1 and isinstance(args[0], dict) and args[0].get("doctype") == "Communication":
                return mock_comm
            return original_get_doc(*args, **kwargs)
            
        original_get_single = frappe.get_single
        def get_single_side_effect(*args, **kwargs):
            if args[0] == "Sift Settings":
                return mock_sift_settings
            return original_get_single(*args, **kwargs)
            
        # Mock frappe.db.get_value to return HTML bio
        original_get_value = frappe.db.get_value
        def get_value_side_effect(*args, **kwargs):
            doctype = kwargs.get("doctype") or (args[0] if len(args) > 0 else None)
            filters = kwargs.get("filters") or (args[1] if len(args) > 1 else None)
            if doctype == "User" and filters == "user@test.com":
                return {"full_name": "Test User", "bio": "<p>I am a <strong>bold</strong> user.</p>"}
            return original_get_value(*args, **kwargs)
            
        with patch.object(frappe, "get_doc", side_effect=get_doc_side_effect):
            with patch.object(frappe, "get_single", side_effect=get_single_side_effect):
                with patch.object(frappe.db, "get_value", side_effect=get_value_side_effect):
                    with patch("frappe_cadence.cadence.multi_channel_cadence.frappe.cache") as mock_cache:
                        mock_cache.return_value.get_value.return_value = None
                        process_cadence_step("MCC-002", "SCHED-002")
                        
                        # Assert
                        mock_post.assert_called_once()
                        data = json.loads(mock_post.call_args[1]["data"])
                        
                        input_data = data["input"]
                        system_content = input_data[0]["content"]
                        
                        self.assertIn("Sender Name: Test User", system_content)
                        self.assertIn("I am a **bold** user.", system_content)
