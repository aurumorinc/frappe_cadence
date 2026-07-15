import frappe
from frappe.tests import IntegrationTestCase
import json

class TestCadenceAstOrm(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        
        frappe.db.rollback()

        # Insert diverse CRM Leads to test all operators
        frappe.get_doc({
            "doctype": "CRM Lead",
            "lead_name": "New Lead AST 1",
            "status": "New",
            "annual_revenue": 60000,
            "email": "test1@example.com"
        }).insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        
        frappe.get_doc({
            "doctype": "CRM Lead",
            "lead_name": "Lost Lead AST 1",
            "status": "Lost",
            "annual_revenue": 40000,
            "email": ""
        }).insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        
        frappe.get_doc({
            "doctype": "CRM Lead",
            "lead_name": "Open Lead AST 1",
            "status": "Open",
            "annual_revenue": 50000,
            "email": "test3@example.com"
        }).insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        frappe.db.commit()

    @classmethod
    def tearDownClass(cls):
        frappe.db.rollback()
        frappe.db.delete("CRM Lead", {"lead_name": ("like", "%AST 1%")})
        frappe.db.delete("Cadence", {"cadence_name": ("like", "%Test AST ORM%")})
        frappe.db.commit()
        super().tearDownClass()
        
    def tearDown(self):
        frappe.db.rollback()
        super().tearDown()

    def _get_cadence_with_condition(self, condition):
        cadence = frappe.new_doc("Cadence")
        cadence.cadence_name = f"Test AST ORM {frappe.generate_hash()}"
        cadence.assign_condition = condition
        cadence.status = "Enabled"
        cadence.save(ignore_permissions=True)
        return cadence

    def test_eq_operator(self):
        cadence = self._get_cadence_with_condition('doc.status == "New"')
        filters = json.loads(cadence.assign_condition_json)
        filters.append(["lead_name", "like", "%AST 1%"])
        leads = frappe.get_all("CRM Lead", filters=filters, pluck="status")
        self.assertEqual(len(leads), 1)
        self.assertEqual(leads[0], "New")

    def test_noteq_operator(self):
        cadence = self._get_cadence_with_condition('doc.status != "Lost"')
        filters = json.loads(cadence.assign_condition_json)
        # Add a filter to only get our test leads
        filters.append(["lead_name", "like", "%AST 1%"])
        leads = frappe.get_all("CRM Lead", filters=filters, pluck="status")
        self.assertEqual(len(leads), 2)
        self.assertNotIn("Lost", leads)

    def test_gt_operator(self):
        cadence = self._get_cadence_with_condition('doc.annual_revenue > 50000')
        filters = json.loads(cadence.assign_condition_json)
        filters.append(["lead_name", "like", "%AST 1%"])
        leads = frappe.get_all("CRM Lead", filters=filters, pluck="annual_revenue")
        self.assertEqual(len(leads), 1)
        self.assertTrue(all(rev > 50000 for rev in leads))

    def test_lt_operator(self):
        cadence = self._get_cadence_with_condition('doc.annual_revenue < 50000')
        filters = json.loads(cadence.assign_condition_json)
        filters.append(["lead_name", "like", "%AST 1%"])
        leads = frappe.get_all("CRM Lead", filters=filters, pluck="annual_revenue")
        self.assertEqual(len(leads), 1)
        self.assertTrue(all(rev < 50000 for rev in leads))

    def test_gte_operator(self):
        cadence = self._get_cadence_with_condition('doc.annual_revenue >= 50000')
        filters = json.loads(cadence.assign_condition_json)
        filters.append(["lead_name", "like", "%AST 1%"])
        leads = frappe.get_all("CRM Lead", filters=filters, pluck="annual_revenue")
        self.assertEqual(len(leads), 2)
        self.assertTrue(all(rev >= 50000 for rev in leads))

    def test_lte_operator(self):
        cadence = self._get_cadence_with_condition('doc.annual_revenue <= 50000')
        filters = json.loads(cadence.assign_condition_json)
        filters.append(["lead_name", "like", "%AST 1%"])
        leads = frappe.get_all("CRM Lead", filters=filters, pluck="annual_revenue")
        self.assertEqual(len(leads), 2)
        self.assertTrue(all(rev <= 50000 for rev in leads))

    def test_in_operator(self):
        cadence = self._get_cadence_with_condition('doc.status in ["New", "Open"]')
        filters = json.loads(cadence.assign_condition_json)
        filters.append(["lead_name", "like", "%AST 1%"])
        leads = frappe.get_all("CRM Lead", filters=filters, pluck="status")
        self.assertEqual(len(leads), 2)
        for s in leads:
            self.assertIn(s, ["New", "Open"])

    def test_notin_operator(self):
        cadence = self._get_cadence_with_condition('doc.status not in ["Lost", "Closed"]')
        filters = json.loads(cadence.assign_condition_json)
        filters.append(["lead_name", "like", "%AST 1%"])
        leads = frappe.get_all("CRM Lead", filters=filters, pluck="status")
        self.assertEqual(len(leads), 2)
        for s in leads:
            self.assertNotIn(s, ["Lost", "Closed"])

    def test_is_operator(self):
        cadence = self._get_cadence_with_condition('doc.email is "set"')
        filters = json.loads(cadence.assign_condition_json)
        filters.append(["lead_name", "like", "%AST 1%"])
        leads = frappe.get_all("CRM Lead", filters=filters, pluck="email")
        self.assertEqual(len(leads), 2)
        for email in leads:
            self.assertTrue(bool(email))

    def test_isnot_operator(self):
        cadence = self._get_cadence_with_condition('doc.email is "not set"')
        filters = json.loads(cadence.assign_condition_json)
        filters.append(["lead_name", "like", "%AST 1%"])
        leads = frappe.get_all("CRM Lead", filters=filters, pluck="email")
        self.assertEqual(len(leads), 1)
        self.assertFalse(bool(leads[0]))
        
    def test_like_operator(self):
        cadence = self._get_cadence_with_condition('doc.email == ["like", "%@example.com"]')
        filters = json.loads(cadence.assign_condition_json)
        filters.append(["lead_name", "like", "%AST 1%"])
        leads = frappe.get_all("CRM Lead", filters=filters, pluck="email")
        self.assertEqual(len(leads), 2)
        for email in leads:
            self.assertTrue(email.endswith("@example.com"))

    def test_notlike_operator(self):
        cadence = self._get_cadence_with_condition('doc.email == ["not like", "%test1%"]')
        filters = json.loads(cadence.assign_condition_json)
        filters.append(["lead_name", "like", "%AST 1%"])
        leads = frappe.get_all("CRM Lead", filters=filters, pluck="email")
        # One is empty string, one is test3@example.com
        self.assertEqual(len(leads), 2)
        for email in leads:
            if email:
                self.assertFalse("test1" in email)

    def test_and_operator(self):
        cadence = self._get_cadence_with_condition('doc.status == "New" and doc.email is "set"')
        filters = json.loads(cadence.assign_condition_json)
        filters.append(["lead_name", "like", "%AST 1%"])
        leads = frappe.get_all("CRM Lead", filters=filters, pluck="status")
        self.assertEqual(len(leads), 1)
        self.assertEqual(leads[0], "New")
