import unittest
from unittest.mock import patch, MagicMock
import frappe
from frappe.tests import UnitTestCase

class MockMultiChannelCadence:
    def __init__(self):
        self.name = "MCC-001"
        self.cadence_name = "Test Cadence"
        self.recipient = "test@example.com"
        self.provider = []
        self.status = "Draft"
        self.flags = {}
        
    def append(self, key, value):
        if key == "provider":
            row = MagicMock()
            row.channel = value.get("channel")
            row.reference_cadence_provider = value.get("reference_cadence_provider")
            self.provider.append(row)

    def get(self, key, default=None):
        if key == "provider":
            return self.provider
        return default

    def has_value_changed(self, key):
        return True
        
    def get_doc_before_save(self):
        m = MagicMock()
        m.status = "Draft"
        return m

class TestMultiChannelCadence(UnitTestCase):

    @patch("frappe_cadence.cadence.doctype.cadence_provider.cadence_provider.resolve_providers_for_mcc")
    def test_mcc_initialization_provider_snapshot(self, mock_resolve):
        from frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence import MultiChannelCadence
        
        # Setup mock
        mock_resolve.return_value = {
            "Email": "Apollo",
            "LinkedIn": "PhantomBuster"
        }
        
        mcc = MockMultiChannelCadence()
        
        # Call the method manually using the class function
        MultiChannelCadence.before_insert(mcc)
        
        mock_resolve.assert_called_once_with("MCC-001")
        self.assertEqual(len(mcc.provider), 2)

        channels = {row.channel: row.reference_cadence_provider for row in mcc.provider}
        self.assertEqual(channels["Email"], "Apollo")
        self.assertEqual(channels["LinkedIn"], "PhantomBuster")

    @patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.frappe.get_all")
    @patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.enqueue")
    @patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.frappe.get_doc")
    def test_mcc_status_change_broadcast(self, mock_get_doc, mock_enqueue, mock_get_all):
        from frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence import MultiChannelCadence
        
        mcc = MockMultiChannelCadence()
        mcc.status = "In Progress"
        
        # Mock parent cadence
        mock_get_doc.return_value = MagicMock() 
        mock_get_all.return_value = []
        
        # Add mock child table
        mcc.append("provider", {"channel": "Email", "reference_cadence_provider": "Apollo"})
        mcc.append("provider", {"channel": "LinkedIn", "reference_cadence_provider": "PhantomBuster"})
        
        # Trigger on_update
        MultiChannelCadence.on_update(mcc)
        
        # Verify enqueue was called for each unique provider
        enqueued_providers = []
        for call in mock_enqueue.call_args_list:
            kwargs = call[1]
            if kwargs.get("event_method") == "on_mcc_status_changed":
                enqueued_providers.append(kwargs.get("provider_name"))
        
        self.assertIn("Apollo", enqueued_providers)
        self.assertIn("PhantomBuster", enqueued_providers)
        self.assertEqual(len(enqueued_providers), 2)
