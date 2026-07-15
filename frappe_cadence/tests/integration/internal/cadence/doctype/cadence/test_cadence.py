import frappe
from frappe.tests import IntegrationTestCase
import json
from unittest.mock import patch

class TestCadenceIntegration(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from frappe.tests.utils import make_test_records
        make_test_records("CRM Lead Status")

    @classmethod
    def tearDownClass(cls):
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
