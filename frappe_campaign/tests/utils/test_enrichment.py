import frappe
from frappe.tests.utils import FrappeTestCase
from frappe_campaign.utils.enrichment import check_and_mark_stale_enrichments
from frappe.utils import add_months, nowdate

class TestEnrichmentUtils(FrappeTestCase):
    def setUp(self):
        # 1. Ensure master data exists
        for status in ["Pending", "Enriched", "Partial", "Stale", "Failed"]:
            if not frappe.db.exists("Enrichment Status", status):
                frappe.get_doc({
                    "doctype": "Enrichment Status",
                    "status": status,
                    "color": "gray"
                }).insert(ignore_permissions=True)

        # 2. Clear test records
        frappe.db.delete("History")
        frappe.db.delete("CRM Lead")
        frappe.db.delete("CRM Organization")

    def create_history(self, ref_dt, ref_dn, months_ago):
        history = frappe.get_doc({
            "doctype": "History",
            "website": "https://example.com",
            "reference_doctype": ref_dt,
            "reference_name": ref_dn
        }).insert(ignore_permissions=True)
        
        # Manually update creation date to simulate old records
        creation_date = add_months(nowdate(), -months_ago)
        frappe.db.set_value("History", history.name, "creation", creation_date, update_modified=False)
        return history

    def test_mark_old_enrichment_as_stale(self):
        lead = frappe.get_doc({
            "doctype": "CRM Lead",
            "first_name": "Old",
            "last_name": "Lead",
            "enrichment_status": "Enriched"
        }).insert(ignore_permissions=True)
        
        # Latest history is 4 months old
        self.create_history("CRM Lead", lead.name, 4)
        
        check_and_mark_stale_enrichments()
        
        self.assertEqual(frappe.db.get_value("CRM Lead", lead.name, "enrichment_status"), "Stale")

    def test_keep_recent_enrichment(self):
        lead = frappe.get_doc({
            "doctype": "CRM Lead",
            "first_name": "Fresh",
            "last_name": "Lead",
            "enrichment_status": "Enriched"
        }).insert(ignore_permissions=True)
        
        # Latest history is 1 month old
        self.create_history("CRM Lead", lead.name, 1)
        
        check_and_mark_stale_enrichments()
        
        self.assertEqual(frappe.db.get_value("CRM Lead", lead.name, "enrichment_status"), "Enriched")

    def test_multiple_history_mixed_ages(self):
        lead = frappe.get_doc({
            "doctype": "CRM Lead",
            "first_name": "Mixed",
            "last_name": "Lead",
            "enrichment_status": "Partial"
        }).insert(ignore_permissions=True)
        
        # Two histories: one old, one new
        self.create_history("CRM Lead", lead.name, 6)
        self.create_history("CRM Lead", lead.name, 0) # today
        
        check_and_mark_stale_enrichments()
        
        self.assertEqual(frappe.db.get_value("CRM Lead", lead.name, "enrichment_status"), "Partial")

    def test_crm_organization_support(self):
        org = frappe.get_doc({
            "doctype": "CRM Organization",
            "organization_name": "Old Corp",
            "enrichment_status": "Enriched"
        }).insert(ignore_permissions=True)
        
        # Latest history is 5 months old
        self.create_history("CRM Organization", org.name, 5)
        
        check_and_mark_stale_enrichments()
        
        self.assertEqual(frappe.db.get_value("CRM Organization", org.name, "enrichment_status"), "Stale")

    def test_ignore_pending_status(self):
        lead = frappe.get_doc({
            "doctype": "CRM Lead",
            "first_name": "Pending",
            "last_name": "Lead",
            "enrichment_status": "Pending"
        }).insert(ignore_permissions=True)
        
        # Has an old history from a previous cycle
        self.create_history("CRM Lead", lead.name, 12)
        
        check_and_mark_stale_enrichments()
        
        # Should stay Pending
        self.assertEqual(frappe.db.get_value("CRM Lead", lead.name, "enrichment_status"), "Pending")

    def test_no_history_remains_unchanged(self):
        lead = frappe.get_doc({
            "doctype": "CRM Lead",
            "first_name": "No",
            "last_name": "History",
            "enrichment_status": "Enriched"
        }).insert(ignore_permissions=True)
        
        check_and_mark_stale_enrichments()
        
        # Should stay Enriched because we can't prove it's stale without history
        self.assertEqual(frappe.db.get_value("CRM Lead", lead.name, "enrichment_status"), "Enriched")
