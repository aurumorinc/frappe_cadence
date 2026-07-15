import frappe
from frappe.tests import IntegrationTestCase
from frappe_cadence.cadence.doctype.cadence_provider.cadence_provider import BaseCadenceProvider
from unittest.mock import patch, MagicMock

class TestProviderIngestion(IntegrationTestCase):
    @classmethod
    def tearDownClass(cls):
        frappe.db.rollback()
        super().tearDownClass()


    @patch("frappe.utils.now")
    @patch("frappe.db.set_value")
    @patch("frappe.get_doc")
    def test_report_event_replied(self, mock_get_doc, mock_set_value, mock_now):
        mock_doc = MagicMock()
        mock_get_doc.return_value = mock_doc
        
        BaseCadenceProvider.report_event("message_replied", {"mcc_name": "MCC-001"})
        
        mock_set_value.assert_called_once_with("Multi Channel Cadence", "MCC-001", "status", "Replied")
        mock_doc.insert.assert_called_once()

    @patch("frappe.utils.now")
    @patch("frappe.db.set_value")
    @patch("frappe.get_doc")
    def test_report_event_bounced(self, mock_get_doc, mock_set_value, mock_now):
        mock_doc = MagicMock()
        mock_get_doc.return_value = mock_doc
        
        BaseCadenceProvider.report_event("bounce", {"mcc_name": "MCC-001"})
        
        mock_set_value.assert_called_once_with("Multi Channel Cadence", "MCC-001", "status", "Bounced")
        mock_doc.insert.assert_called_once()

    @patch("frappe.utils.now")
    @patch("frappe.db.set_value")
    @patch("frappe.get_doc")
    def test_report_event_sent_opened(self, mock_get_doc, mock_set_value, mock_now):
        mock_doc = MagicMock()
        mock_get_doc.return_value = mock_doc
        
        BaseCadenceProvider.report_event("message_sent", {"communication_name": "COMM-001", "mcc_name": "MCC-001"})
        
        mock_set_value.assert_called_once_with("Communication", "COMM-001", "delivery_status", "Sent")
        mock_doc.insert.assert_called_once()
        
        mock_set_value.reset_mock()
        mock_doc.insert.reset_mock()
        
        BaseCadenceProvider.report_event("message_opened", {"communication_name": "COMM-001", "mcc_name": "MCC-001"})
        
        mock_set_value.assert_called_once_with("Communication", "COMM-001", "read_status", "Read")
        mock_doc.insert.assert_called_once()
