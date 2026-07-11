import frappe
from frappe.tests import IntegrationTestCase

class TestEnrichmentUtils(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        frappe.db.rollback()
        super().tearDownClass()

    def setUp(self):
        # Clear test records
        frappe.db.delete("History")
        frappe.db.delete("CRM Lead")
        frappe.db.delete("CRM Organization")

    def tearDown(self):
        frappe.db.rollback()

    def test_get_crm_leads(self):
        leads = []
        for i in range(1, 4):
            lead = frappe.get_doc({
                "doctype": "CRM Lead",
                "first_name": f"Test{i}",
                "email_id": f"test{i}@example.com"
            }).insert(ignore_permissions=True)
            leads.append(lead.name)

        if not frappe.db.exists("Email Template", "_Test Email Template"):
            frappe.get_doc({
                "doctype": "Email Template",
                "name": "_Test Email Template",
                "subject": "Test",
                "response": "Test"
            }).insert(ignore_permissions=True)

        cadence = frappe.get_doc({
            "doctype": "Cadence",
            "cadence_name": "Test Cadence Enrich",
            "cadence_schedules": [
                {
                    "reference_doctype": "Email Template",
                    "reference_name": "_Test Email Template",
                    "send_after_days": 1
                }
            ]
        }).insert(ignore_permissions=True)
            
        mcc_data = [
            ("Draft", leads[0]),
            ("Provisioning", leads[1]),
            ("Error", leads[2])
        ]
        
        for status, lead_name in mcc_data:
            frappe.get_doc({
                "doctype": "Multi Channel Cadence",
                "cadence_name": cadence.name,
                "recipient": lead_name,
                "status": status,
                "start_date": frappe.utils.nowdate()
            }).insert(ignore_permissions=True)
            
        from frappe_cadence.utils.enrichment import get_crm_leads
        
        results = get_crm_leads(
            doctype="Email Template Annotation",
            txt="",
            searchfield="name",
            start=0,
            page_len=20,
            filters={"template_name": "_Test Email Template"}
        )
        
        lead_names = [r[0] for r in results]
        
        self.assertIn(leads[0], lead_names)
        self.assertNotIn(leads[1], lead_names)
        self.assertNotIn(leads[2], lead_names)
