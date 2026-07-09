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
    @patch("frappe_cadence.cadence.multi_channel_cadence.today", return_value="2026-01-01")
    @patch("frappe_cadence.cadence.multi_channel_cadence.frappe.db.get_value")
    def test_process_cadence_step_sift_integration(self, mock_get_value, mock_today, mock_get_url, mock_get_all, mock_wait_for_event, mock_post):
        mock_get_value.return_value = {"full_name": "Mock User", "bio": "Mock Bio"}
        mock_get_url.return_value = "http://test.com/webhook"
        from frappe_cadence.cadence.multi_channel_cadence import process_cadence_step
        
        # Mock get_all to return empty for idempotency check and draft comm check
        mock_get_all.return_value = []
        
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
            
        with patch.object(frappe, "get_doc", side_effect=get_doc_side_effect):
            with patch.object(frappe, "get_single", side_effect=get_single_side_effect):
                with patch("frappe_cadence.cadence.multi_channel_cadence.frappe.cache") as mock_cache:
                    mock_cache.return_value.get_value.return_value = None
                    process_cadence_step("MCC-001", "SCHED-001")
                    
                    # Assert
                    mock_post.assert_called_once()
                    called_url = mock_post.call_args[0][0]
                    self.assertEqual(called_url, "https://api.sift.com/agents")
                    
                    headers = mock_post.call_args[1]["headers"]
                    self.assertEqual(headers["Authorization"], "Bearer sift_secret_key")
                    
                    data = mock_post.call_args[1]["data"]
                    self.assertIn("webhook_url", data)
                    self.assertIn("http://test.com/webhook", data)
                    
                    mock_wait_for_event.assert_called_once_with(
                        "callback",
                        condition="argument.get('communication_id') == 'COMM-001'"
                    )
