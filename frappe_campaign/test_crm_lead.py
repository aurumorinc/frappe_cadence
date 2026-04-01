import frappe
from frappe.tests import IntegrationTestCase
from frappe_campaign.crm_lead import get as get_crm_leads

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
        
        # 2. Create Campaign
        cls.campaign1 = frappe.get_doc({
            "doctype": "Campaign",
            "campaign_name": "_Test Campaign 1"
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
        
        # 4. Link Lead 1 to Campaign 1
        frappe.get_doc({
            "doctype": "CRM Lead Campaign",
            "parent": cls.lead1.name,
            "parenttype": "CRM Lead",
            "parentfield": "campaigns",
            "campaign_name": cls.campaign1.name
        }).insert(ignore_permissions=True, ignore_mandatory=True, ignore_links=True)

    @classmethod
    def tearDownClass(cls):
        frappe.db.rollback()
        super().tearDownClass()

    def test_get_leads_without_campaign_exclusion(self):
        filters = '[["CRM Lead", "source", "=", "Cold Email"]]'
        leads = get_crm_leads(filters=filters, fields='["name", "organization"]')
        
        lead_names = [l.name for l in leads]
        self.assertIn(self.lead1.name, lead_names)
        self.assertIn(self.lead2.name, lead_names)
        self.assertNotIn(self.lead3.name, lead_names)

    def test_get_leads_with_campaign_exclusion(self):
        # We simulate the exact n8n filter
        filters = f'[["CRM Lead Campaign", "name", "not in", ["{self.campaign1.name}"]], ["CRM Lead", "source", "=", "Cold Email"]]'
        leads = get_crm_leads(filters=filters, fields='["name", "organization"]')
        
        # lead1 should be excluded because it's in _Test Campaign 1
        lead_names = [l.name for l in leads]
        self.assertNotIn(self.lead1.name, lead_names)
        self.assertIn(self.lead2.name, lead_names)

    def test_get_leads_with_limit(self):
        # We have lead1 and lead2 with Cold Email source
        filters = '[["CRM Lead", "source", "=", "Cold Email"]]'
        leads = get_crm_leads(filters=filters, fields='["name"]', limit=1)
        
        self.assertEqual(len(leads), 1)
