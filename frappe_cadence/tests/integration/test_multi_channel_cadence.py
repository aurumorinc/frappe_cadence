import frappe
from frappe.tests import UnitTestCase
from unittest.mock import patch, MagicMock
from frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence import MultiChannelCadence

class TestMultiChannelCadenceLifecycle(UnitTestCase):

    @patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.frappe.get_all")
    @patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.enqueue")
    @patch("frappe.get_doc")
    def test_mcc_status_update_triggers_broadcast(self, mock_get_doc, mock_enqueue, mock_get_all):
        mock_get_all.return_value = []
        mock_cadence = MagicMock()
        mock_cadence.provider = "Dummy"
        mock_get_doc.return_value = mock_cadence
        
        mcc = MultiChannelCadence({"doctype": "Multi Channel Cadence"})
        mcc.cadence_name = "Cadence-1"
        mcc.status = "Scheduled"
        mcc.provider = [MagicMock(reference_cadence_provider="Dummy")]
        mcc.get_doc_before_save = MagicMock(return_value=MagicMock(status="Draft"))
        mcc.has_value_changed = MagicMock(return_value=True)
        
        mcc.on_update()
        
        mock_enqueue.assert_called_with(
            "frappe_cadence.cadence.doctype.cadence_provider.cadence_provider.broadcast_event",
            queue="low",
            provider_name="Dummy",
            event_method="on_mcc_status_changed",
            mcc_doc=mcc,
            old_status="Draft",
            new_status="Scheduled",
            now=True
        )

    @patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.frappe.get_all")
    @patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.enqueue")
    @patch("frappe.get_doc")
    def test_provider_agnostic_mcc_lifecycle(self, mock_get_doc, mock_enqueue, mock_get_all):
        mock_get_all.return_value = []
        mock_cadence = MagicMock()
        mock_cadence.provider = None
        sch = MagicMock()
        sch.name = "Sch-1"
        mock_cadence.cadence_schedules = [sch]
        mock_get_doc.return_value = mock_cadence
        
        mcc = MultiChannelCadence({"doctype": "Multi Channel Cadence"})
        mcc.cadence_name = "Cadence-1"
        mcc.status = "Scheduled"
        mcc.name = "MCC-1"
        mcc.provider = []
        mcc.get_doc_before_save = MagicMock(return_value=MagicMock(status="Draft"))
        mcc.has_value_changed = MagicMock(return_value=True)
        
        mcc.on_update()
        
        # enqueue should NOT be called for broadcast_event
        for call in mock_enqueue.call_args_list:
            self.assertNotEqual(call[0][0], "frappe_cadence.cadence.doctype.cadence_provider.cadence_provider.broadcast_event")

        # It should enqueue the native process_cadence_step
        mock_enqueue.assert_any_call(
            "frappe_cadence.cadence.multi_channel_cadence.process_cadence_step",
            queue="default",
            cadence_name="MCC-1",
            schedule_name="Sch-1",
            previous_schedule_name=None,
            now=True
        )
