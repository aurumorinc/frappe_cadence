from frappe.tests import IntegrationTestCase
from unittest.mock import patch, MagicMock
import frappe
from frappe_cadence.cadence.email_template import callback

class TestCallback(IntegrationTestCase):
    
    @patch("frappe_cadence.cadence.email_template.emit_event")
    @patch("frappe_cadence.cadence.email_template.frappe.get_doc")
    def test_callback_emits_event(self, mock_get_doc, mock_emit_event):
        # Mock payload
        frappe.local.request = frappe._dict(json={
            "type": "response.completed",
            "metadata": {
                "name": "COMM-001"
            },
            "data": [
                {
                    "content": [
                        {
                            "text": "{\"subject\": \"Hello\", \"content\": \"Hi there\"}"
                        }
                    ]
                }
            ]
        })
        
        mock_comm = MagicMock()
        mock_comm.communication_medium = "Email"
        mock_get_doc.return_value = mock_comm
        
        result = callback()
        
        self.assertEqual(result.get("status"), "success")
        self.assertEqual(mock_comm.subject, "Hello")
        self.assertEqual(mock_comm.content, "Hi there")
        mock_comm.save.assert_called_once_with(ignore_permissions=True)
        
        mock_emit_event.assert_called_once_with("callback", {"communication_id": "COMM-001"})

    def test_callback_missing_communication_id(self):
        frappe.local.request = frappe._dict(json={
            "metadata": {},
            "output": [{"content": [{"text": "{}"}]}]
        })
        result = callback()
        self.assertEqual(result.get("status"), "error")
        self.assertEqual(result.get("message"), "Missing communication_id in metadata")

    def test_callback_missing_output_text(self):
        frappe.local.request = frappe._dict(json={
            "metadata": {"name": "COMM-001"},
            "output": [{"content": [{}]}]
        })
        result = callback()
        self.assertEqual(result.get("status"), "error")
        self.assertEqual(result.get("message"), "Missing output text")

    def test_callback_invalid_json(self):
        frappe.local.request = frappe._dict(json={
            "type": "response.completed",
            "metadata": {"name": "COMM-001"},
            "data": [{"content": [{"text": "invalid json"}]}]
        })
        result = callback()
        self.assertEqual(result.get("status"), "error")
        self.assertIn("Expecting value", result.get("message"))
