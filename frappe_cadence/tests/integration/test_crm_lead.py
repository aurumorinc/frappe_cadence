import frappe
from frappe.tests import IntegrationTestCase
from frappe_cadence.crm_lead import get as get_crm_leads

class TestCRMLead(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        
        # 1. Create Organizations
        cls.org1 = frappe.get_doc({
            "doctype": "CRM Organization",
            "organization_name": "_Test Org 1"
        }).insert(ignore_permissions=True, ignore_mandatory=True, ignore_links=True)
        
        cls.org2 = frappe.get_doc({
            "doctype": "CRM Organization",
            "organization_name": "_Test Org 2"
        }).insert(ignore_permissions=True, ignore_mandatory=True, ignore_links=True)
        
        # 2. Create Cadence
        cls.cadence1 = frappe.get_doc({
            "doctype": "Cadence",
            "cadence_name": "_Test Cadence 1"
        }).insert(ignore_permissions=True, ignore_mandatory=True, ignore_links=True)
        
        # 3. Create Leads
        cls.lead1 = frappe.get_doc({
            "doctype": "CRM Lead",
            "first_name": "Test Lead 1",
            "source": "Cold Email",
            "email": "test1@example.com",
            "organization": cls.org1.name
        }).insert(ignore_permissions=True, ignore_mandatory=True, ignore_links=True)
        
        cls.lead2 = frappe.get_doc({
            "doctype": "CRM Lead",
            "first_name": "Test Lead 2",
            "source": "Cold Email",
            "email": "test2@example.com",
            "organization": cls.org2.name
        }).insert(ignore_permissions=True, ignore_mandatory=True, ignore_links=True)
        
        cls.lead3 = frappe.get_doc({
            "doctype": "CRM Lead",
            "first_name": "Test Lead 3",
            "source": "Website",
            "email": "test3@example.com",
            "organization": cls.org2.name
        }).insert(ignore_permissions=True, ignore_mandatory=True, ignore_links=True)
        
        # 4. Link Lead 1 to Cadence 1
        frappe.get_doc({
            "doctype": "CRM Lead Cadence",
            "parent": cls.lead1.name,
            "parenttype": "CRM Lead",
            "parentfield": "cadences",
            "cadence_name": cls.cadence1.name
        }).insert(ignore_permissions=True, ignore_mandatory=True, ignore_links=True)

    @classmethod
    def tearDownClass(cls):
        frappe.db.rollback()
        super().tearDownClass()

    def test_get_leads_without_cadence_exclusion(self):
        filters = '[["CRM Lead", "source", "=", "Cold Email"]]'
        leads = get_crm_leads(filters=filters, fields='["name", "organization"]')
        
        lead_names = [l.name for l in leads]
        self.assertIn(self.lead1.name, lead_names)
        self.assertIn(self.lead2.name, lead_names)
        self.assertNotIn(self.lead3.name, lead_names)

    def test_get_leads_with_cadence_exclusion(self):
        # We simulate the exact n8n filter
        filters = f'[["CRM Lead Cadence", "name", "not in", ["{self.cadence1.name}"]], ["CRM Lead", "source", "=", "Cold Email"]]'
        leads = get_crm_leads(filters=filters, fields='["name", "organization"]')
        
        # lead1 should be excluded because it's in _Test Cadence 1
        lead_names = [l.name for l in leads]
        self.assertNotIn(self.lead1.name, lead_names)
        self.assertIn(self.lead2.name, lead_names)

    def test_get_leads_with_limit(self):
        # We have lead1 and lead2 with Cold Email source
        filters = '[["CRM Lead", "source", "=", "Cold Email"]]'
        leads = get_crm_leads(filters=filters, fields='["name"]', limit=1)
        
        self.assertEqual(len(leads), 1)
