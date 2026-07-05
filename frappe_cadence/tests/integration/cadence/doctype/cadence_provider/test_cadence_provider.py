import frappe
from frappe.tests import IntegrationTestCase
from frappe_cadence.cadence.doctype.cadence_provider.cadence_provider import CadenceProviderBase

class TestCadenceProviderIntegration(IntegrationTestCase):
    def setUp(self):
        existing_cadence = frappe.db.exists("Cadence", {"cadence_name": "Test Cadence"})
        if not existing_cadence:
            cadence = frappe.get_doc({
                "doctype": "Cadence",
                "cadence_name": "Test Cadence",
            }).insert(ignore_permissions=True, ignore_if_duplicate=True)
            self.cadence_name = cadence.name
        else:
            self.cadence_name = existing_cadence
            
        existing_lead = frappe.db.exists("CRM Lead", {"lead_name": "Test Lead"})
        if not existing_lead:
            lead = frappe.get_doc({
                "doctype": "CRM Lead",
                "first_name": "Test",
                "lead_name": "Test Lead"
            }).insert(ignore_permissions=True, ignore_if_duplicate=True)
            self.lead_name = lead.name
        else:
            self.lead_name = existing_lead
            
        mcc = frappe.get_all("Multi Channel Cadence", filters={"cadence_name": self.cadence_name, "recipient": self.lead_name})
        if not mcc:
            mcc_doc = frappe.get_doc({
                "doctype": "Multi Channel Cadence",
                "cadence_name": self.cadence_name,
                "cadence_for": "CRM Lead",
                "recipient": self.lead_name,
                "status": "In Progress",
                "start_date": frappe.utils.nowdate()
            }).insert(ignore_permissions=True)
            self.mcc_name = mcc_doc.name
        else:
            self.mcc_name = mcc[0].name

    def test_report_event_replied(self):
        # Emulate webhook
        CadenceProviderBase.report_event(
            event_type="message_replied",
            context={"mcc_name": self.mcc_name},
            data={"id": "evt_123"}
        )
        
        # Verify MCC state
        mcc_status = frappe.db.get_value("Multi Channel Cadence", self.mcc_name, "status")
        self.assertEqual(mcc_status, "Replied")
        
        # Verify History creation
        history = frappe.get_all("History", filters={
            "reference_doctype": "Multi Channel Cadence",
            "reference_name": self.mcc_name,
            "content": "Replied"
        })
        self.assertTrue(len(history) > 0)
