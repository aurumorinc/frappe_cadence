import frappe
from frappe.tests import IntegrationTestCase

class TestEnrichmentFlow(IntegrationTestCase):
    def setUp(self):
        # Create test records needed
        if not frappe.db.exists("Email Template", "_Test Email Template Flow"):
            frappe.get_doc({
                "doctype": "Email Template",
                "name": "_Test Email Template Flow",
                "subject": "Test",
                "response": "Test"
            }).insert(ignore_permissions=True)
            
        lead = frappe.get_doc({
            "doctype": "CRM Lead",
            "email_id": "flowtest@example.com",
            "first_name": "Flow"
        }).insert(ignore_permissions=True)
        self.lead_name = lead.name
            
        if not frappe.db.exists("User", "test_flow@example.com"):
            frappe.get_doc({
                "doctype": "User",
                "email": "test_flow@example.com",
                "first_name": "Flow",
                "send_welcome_email": 0
            }).insert(ignore_permissions=True)
            
    def test_enrichment_pipeline(self):
        # 1. Create a Cadence
        cadence = frappe.get_doc({
            "doctype": "Cadence",
            "cadence_name": "Test Cadence Flow",
            "cadence_code": "CAD-TEST-FLOW",
            "cadence_schedules": [
                {
                    "reference_doctype": "Email Template",
                    "reference_name": "_Test Email Template Flow",
                    "send_after_days": 1
                }
            ],
            "users": [
                {"user": "test_flow@example.com"}
            ]
        }).insert(ignore_permissions=True)
        
        # Verify Playbook creation
        self.assertTrue(cadence.reference_playbook)
        playbook = frappe.get_doc("Playbook", cadence.reference_playbook)
        self.assertEqual(playbook.document_type, "Multi Channel Cadence")
        
        # 2. Trigger lead assignment
        from frappe_cadence.cadence.doctype.cadence.cadence import add_lead_to_cadence
        add_lead_to_cadence(cadence, self.lead_name)
        
        mcc_records = frappe.get_all("Multi Channel Cadence", filters={"cadence_name": cadence.name, "recipient": self.lead_name})
        self.assertEqual(len(mcc_records), 1)
        mcc = frappe.get_doc("Multi Channel Cadence", mcc_records[0].name)
        
        # Verify default status is Provisioning
        self.assertEqual(mcc.status, "Provisioning")
        
        # 3. Try to get leads for annotation
        from frappe_cadence.utils.enrichment import get_crm_leads
        results = get_crm_leads(
            doctype="Annotation",
            txt="",
            searchfield="name",
            start=0,
            page_len=20,
            filters={"template_name": "_Test Email Template Flow"}
        )
        
        # Lead should NOT appear yet because it's Provisioning
        lead_names = [r[0] for r in results]
        self.assertNotIn(self.lead_name, lead_names)
        
        # 4. Simulate Playbook completion by setting to Draft
        mcc.status = "Draft"
        mcc.save(ignore_permissions=True)
        
        # 5. Lead should now appear
        results = get_crm_leads(
            doctype="Annotation",
            txt="",
            searchfield="name",
            start=0,
            page_len=20,
            filters={"template_name": "_Test Email Template Flow"}
        )
        lead_names = [r[0] for r in results]
        self.assertIn(self.lead_name, lead_names)
