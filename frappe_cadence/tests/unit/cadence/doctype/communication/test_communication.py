import unittest
from unittest.mock import patch, MagicMock
import frappe
from frappe.tests import UnitTestCase

from frappe_cadence.cadence.doctype.communication.communication import on_communication_update, after_communication_insert

class TestCommunicationEvents(UnitTestCase):

    @patch("frappe_cadence.cadence.doctype.communication.communication.enqueue")
    def test_on_communication_update_provider_routing(self, mock_enqueue):
        doc = MagicMock()
        doc.reference_doctype = "Multi Channel Cadence"
        doc.reference_name = "MCC-001"
        doc.get.return_value = "Apollo"
        doc.has_value_changed.return_value = True
        doc.delivery_status = "Scheduled"
        doc.get_doc_before_save.return_value.delivery_status = "Open"
        
        on_communication_update(doc)
        
        doc.get.assert_called_with("reference_cadence_provider")
        mock_enqueue.assert_called_once_with(
            "frappe_cadence.cadence.doctype.cadence_provider.cadence_provider.broadcast_event",
            queue="low",
            provider_name="Apollo",
            event_method="on_communication_status_changed",
            comm_doc=doc,
            old_status="Open",
            new_status="Scheduled"
        )

    @patch("frappe_cadence.cadence.doctype.communication.communication.enqueue")
    def test_after_communication_insert_provider_routing(self, mock_enqueue):
        doc = MagicMock()
        doc.reference_doctype = "Multi Channel Cadence"
        doc.reference_name = "MCC-001"
        doc.get.return_value = "SendGrid"
        
        after_communication_insert(doc)
        
        doc.get.assert_called_with("reference_cadence_provider")
        mock_enqueue.assert_called_once_with(
            "frappe_cadence.cadence.doctype.cadence_provider.cadence_provider.broadcast_event",
            queue="low",
            provider_name="SendGrid",
            event_method="after_communication_insertd",
            comm_doc=doc
        )
