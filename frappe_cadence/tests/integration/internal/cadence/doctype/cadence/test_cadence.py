import frappe
from frappe.tests import IntegrationTestCase
import json
from unittest.mock import patch

class TestCadenceIntegration(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.patcher = patch('frappe_controller.utils.controller.emit_event')
        cls.mock_emit = cls.patcher.start()
        cls.patcher2 = patch('frappe.utils.global_search.sync_value_in_queue')
        cls.mock_gs = cls.patcher2.start()
        cls.patcher3 = patch('frappe.enqueue')
        cls.mock_enq = cls.patcher3.start()
        cls.patcher4 = patch('frappe_controller.utils.background_jobs.enqueue')
        cls.mock_fc_enq = cls.patcher4.start()
        from frappe.tests.utils import make_test_records
        make_test_records("CRM Lead Status")

    @classmethod
    def tearDownClass(cls):
        cls.patcher.stop()
        cls.patcher2.stop()
        cls.patcher3.stop()
        cls.patcher4.stop()
        frappe.db.rollback()
        super().tearDownClass()

    def tearDown(self):
        frappe.db.rollback()
        super().tearDown()

    def test_ast_parser_conversion_sync(self):
        # Create a Cadence with assign_condition
        cadence = frappe.get_doc({
            "doctype": "Cadence",
            "cadence_name": "Test AST Sync",
            "assign_condition": 'doc.status == "New" and doc.source == "API"',
            "status": "Enabled"
        }).insert(ignore_permissions=True)

        expected_filters = [["status", "=", "New"], ["source", "=", "API"]]
        self.assertEqual(json.loads(cadence.assign_condition_json), expected_filters)

    def test_ast_parser_validation_failure(self):
        with self.assertRaises(frappe.ValidationError):
            frappe.get_doc({
                "doctype": "Cadence",
                "cadence_name": "Test AST Invalid",
                "assign_condition": 'doc.status.startswith("N")',
                "status": "Enabled"
            }).insert(ignore_permissions=True)

    def test_evaluate_cadence_for_leads(self):
        # Create a Cadence matching leads with status "New"
        cadence = frappe.get_doc({
            "doctype": "Cadence",
            "cadence_name": "Test Eval Cadence",
            "assign_condition": 'doc.status == "New"',
            "status": "Enabled"
        }).insert(ignore_permissions=True)

        # Insert a matching Lead
        lead_new = frappe.get_doc({
            "doctype": "CRM Lead",
            "first_name": "Test",
            "lead_name": "Test Eval Lead New",
            "status": "New"
        }).insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)

        # Insert a non-matching Lead
        lead_replied = frappe.get_doc({
            "doctype": "CRM Lead",
            "first_name": "Test",
            "lead_name": "Test Eval Lead Replied",
            "status": "Replied"
        }).insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)

        from frappe_cadence.cadence.doctype.cadence.cadence import evaluate_cadence_for_leads
        evaluate_cadence_for_leads(cadence.name)

        # Check if MCC is spawned for matching lead
        mcc_new = frappe.get_all("Multi Channel Cadence", filters={
            "cadence_name": cadence.name,
            "recipient": lead_new.name
        })
        self.assertTrue(len(mcc_new) > 0, "Multi Channel Cadence was not spawned for the matching lead.")

        # Check if MCC is NOT spawned for non-matching lead
        mcc_replied = frappe.get_all("Multi Channel Cadence", filters={
            "cadence_name": cadence.name,
            "recipient": lead_replied.name
        })
        self.assertEqual(len(mcc_replied), 0, "Multi Channel Cadence was incorrectly spawned for non-matching lead.")

    def test_evaluate_lead_for_cadences(self):
        # Create a Cadence matching leads with territory "India"
        cadence = frappe.get_doc({
            "doctype": "Cadence",
            "cadence_name": "Test Eval Lead Cadence",
            "assign_condition": 'doc.territory == "India"',
            "status": "Enabled"
        }).insert(ignore_permissions=True)

        lead = frappe.get_doc({
            "doctype": "CRM Lead",
            "first_name": "Test",
            "lead_name": "Test Eval Lead Territory",
            "territory": "India"
        }).insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)

        from frappe_cadence.cadence.doctype.cadence.cadence import evaluate_lead_for_cadences
        evaluate_lead_for_cadences(lead.name)

        # Check if MCC is spawned
        mcc = frappe.get_all("Multi Channel Cadence", filters={
            "cadence_name": cadence.name,
            "recipient": lead.name
        })
        self.assertTrue(len(mcc) > 0, "Multi Channel Cadence was not spawned for the JSON lead.")

    def test_idempotency_enrollment(self):
        cadence = frappe.get_doc({
            "doctype": "Cadence",
            "cadence_name": f"Test Idempotency Cadence {frappe.generate_hash()}",
            "assign_condition": 'doc.status == "New"',
            "status": "Enabled"
        }).insert(ignore_permissions=True)

        lead = frappe.get_doc({
            "doctype": "CRM Lead",
            "first_name": "Test",
            "lead_name": f"Test Idempotency Lead {frappe.generate_hash()}",
            "status": "New"
        }).insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)

        from frappe_cadence.cadence.doctype.cadence.cadence import evaluate_lead_for_cadences
        evaluate_lead_for_cadences(lead.name)
        evaluate_lead_for_cadences(lead.name)

        mccs = frappe.get_all("Multi Channel Cadence", filters={
            "cadence_name": cadence.name,
            "recipient": lead.name
        })
        self.assertEqual(len(mccs), 1, "Expected exactly 1 MCC, but idempotency failed.")

    def test_round_robin_assignment(self):
        # Create Users
        users = []
        for i in range(3):
            email = f"rr_user_{i}@example.com"
            if not frappe.db.exists("User", email):
                frappe.get_doc({"doctype": "User", "email": email, "first_name": f"RR {i}", "send_welcome_email": 0}).insert(ignore_permissions=True)
            users.append(email)

        cadence = frappe.get_doc({
            "doctype": "Cadence",
            "cadence_name": f"Test RR Cadence {frappe.generate_hash()}",
            "assign_condition": 'doc.status == "New"',
            "status": "Enabled",
            "rule": "Round Robin"
        })
        for u in users:
            cadence.append("users", {"user": u})
        cadence.insert(ignore_permissions=True)

        from frappe_cadence.cadence.doctype.cadence.cadence import add_lead_to_cadence
        
        assigned_users = []
        for i in range(4):
            lead = frappe.get_doc({
                "doctype": "CRM Lead",
                "lead_name": f"Test RR Lead {i} {frappe.generate_hash()}",
                "status": "New"
            }).insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
            
            add_lead_to_cadence(cadence, lead.name)
            
            # Re-fetch the cadence to get the updated last_user
            cadence.reload()
            
            mccs = frappe.get_all("Multi Channel Cadence", filters={"cadence_name": cadence.name, "recipient": lead.name}, fields=["sender"])
            assigned_users.append(mccs[0].sender)
            
        self.assertEqual(assigned_users[0], users[0])
        self.assertEqual(assigned_users[1], users[1])
        self.assertEqual(assigned_users[2], users[2])
        self.assertEqual(assigned_users[3], users[0])

    def test_load_balancing_assignment(self):
        # Create Users
        users = []
        for i in range(2):
            email = f"lb_user_{i}@example.com"
            if not frappe.db.exists("User", email):
                frappe.get_doc({"doctype": "User", "email": email, "first_name": f"LB {i}", "send_welcome_email": 0}).insert(ignore_permissions=True)
            users.append(email)

        cadence = frappe.get_doc({
            "doctype": "Cadence",
            "cadence_name": f"Test LB Cadence {frappe.generate_hash()}",
            "assign_condition": 'doc.status == "New"',
            "status": "Enabled",
            "rule": "Load Balancing"
        })
        for u in users:
            cadence.append("users", {"user": u})
        cadence.insert(ignore_permissions=True)

        # Manually create 5 active MCCs for User A and 1 for User B
        for i in range(5):
            dummy_a = frappe.get_doc({
                "doctype": "CRM Lead",
                "lead_name": f"Dummy Lead A {i} {frappe.generate_hash()}"
            }).insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
            
            frappe.get_doc({
                "doctype": "Multi Channel Cadence",
                "cadence_name": cadence.name,
                "cadence_for": "CRM Lead",
                "recipient": dummy_a.name,
                "sender": users[0],
                "status": "In Progress"
            }).insert(ignore_permissions=True)
            
        dummy_b = frappe.get_doc({
            "doctype": "CRM Lead",
            "lead_name": f"Dummy Lead B 0 {frappe.generate_hash()}"
        }).insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        
        frappe.get_doc({
            "doctype": "Multi Channel Cadence",
            "cadence_name": cadence.name,
            "cadence_for": "CRM Lead",
            "recipient": dummy_b.name,
            "sender": users[1],
            "status": "In Progress"
        }).insert(ignore_permissions=True)

        from frappe_cadence.cadence.doctype.cadence.cadence import add_lead_to_cadence
        
        lead = frappe.get_doc({
            "doctype": "CRM Lead",
            "lead_name": f"Test LB Lead {frappe.generate_hash()}",
            "status": "New"
        }).insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        
        add_lead_to_cadence(cadence, lead.name)
        
        mccs = frappe.get_all("Multi Channel Cadence", filters={"cadence_name": cadence.name, "recipient": lead.name}, fields=["sender"])
        
        # User B should be assigned because they have 1 vs User A's 5
        self.assertEqual(mccs[0].sender, users[1])

    def test_evaluate_cadence_invalid_json(self):
        # Create a Cadence with invalid JSON assignment rule
        cadence = frappe.get_doc({
            "doctype": "Cadence",
            "cadence_name": "Test Invalid JSON Cadence",
            "status": "Enabled"
        }).insert(ignore_permissions=True)
        # Directly bypass before_save to set invalid JSON
        cadence.db_set("assign_condition_json", "INVALID_JSON")

        from frappe_cadence.cadence.doctype.cadence.cadence import evaluate_cadence_for_leads

        with patch("frappe_cadence.cadence.doctype.cadence.cadence.frappe.log_error") as mock_log_error:
            evaluate_cadence_for_leads(cadence.name)
            mock_log_error.assert_called_once()
            self.assertEqual(mock_log_error.call_args[1]["title"], "Invalid Cadence Assign Condition JSON")

    def test_evaluate_lead_invalid_json(self):
        # Create a Cadence with invalid JSON assignment rule
        cadence = frappe.get_doc({
            "doctype": "Cadence",
            "cadence_name": "Test Invalid JSON Cadence 2",
            "status": "Enabled"
        }).insert(ignore_permissions=True)
        # Directly bypass before_save to set invalid JSON
        cadence.db_set("assign_condition_json", "INVALID_JSON")

        lead = frappe.get_doc({
            "doctype": "CRM Lead",
            "first_name": "Test",
            "lead_name": "Test Invalid Lead"
        }).insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)

        from frappe_cadence.cadence.doctype.cadence.cadence import evaluate_lead_for_cadences

        with patch("frappe_cadence.cadence.doctype.cadence.cadence.frappe.log_error") as mock_log_error:
            evaluate_lead_for_cadences(lead.name)

            # evaluate_lead_for_cadences iterates over all cadences.
            # We just need to check if the error was logged for our invalid cadence.
            calls = mock_log_error.call_args_list
            self.assertTrue(any(call[1].get("title") == "Error evaluating Cadence assignment JSON" for call in calls))
import frappe
from frappe.tests import IntegrationTestCase
import json

class TestCadenceAstOrm(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.patcher = patch('frappe_controller.utils.controller.emit_event')
        cls.mock_emit = cls.patcher.start()
        cls.patcher2 = patch('frappe.utils.global_search.sync_value_in_queue')
        cls.mock_gs = cls.patcher2.start()
        cls.patcher3 = patch('frappe.enqueue')
        cls.mock_enq = cls.patcher3.start()
        cls.patcher4 = patch('frappe_controller.utils.background_jobs.enqueue')
        cls.mock_fc_enq = cls.patcher4.start()

    @classmethod
    def tearDownClass(cls):
        cls.patcher.stop()
        cls.patcher2.stop()
        cls.patcher3.stop()
        cls.patcher4.stop()
        frappe.db.rollback()
        super().tearDownClass()

    def setUp(self):
        super().setUp()
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
