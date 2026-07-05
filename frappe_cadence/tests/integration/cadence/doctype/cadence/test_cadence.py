import frappe
from frappe.tests import IntegrationTestCase
import json
from unittest.mock import patch

class TestCadenceIntegration(IntegrationTestCase):
    def setUp(self):
        # Create a Cadence with a JSON assignment rule matching leads with country "India"
        existing = frappe.db.exists("Cadence", {"cadence_name": "Test Lead Cadence"})
        if not existing:
            cadence = frappe.get_doc({
                "doctype": "Cadence",
                "cadence_name": "Test Lead Cadence",
                "assign_condition_json": json.dumps([["country", "=", "India"]]),
                "status": "Enabled"
            }).insert(ignore_permissions=True)
            self.cadence_name = cadence.name
        else:
            self.cadence_name = existing

    def test_lead_evaluation_spawns_mcc(self):
        # Insert a matching Lead
        lead = frappe.get_doc({
            "doctype": "CRM Lead",
            "first_name": "Test",
            "lead_name": "Test India Lead",
            "country": "India"
        }).insert(ignore_permissions=True)
        
        # Add to cadence using evaluate_cadence_for_leads or manually add
        # Because JSON evaluator uses DB queries, let's just make sure the lead is saved
        lead.save(ignore_permissions=True)
        
        from frappe_cadence.cadence.doctype.cadence.cadence import add_lead_to_cadence
        cadence = frappe.get_doc("Cadence", self.cadence_name)
        add_lead_to_cadence(cadence, lead.name)
        
        # Check if MCC is spawned
        mcc = frappe.get_all("Multi Channel Cadence", filters={
            "cadence_name": self.cadence_name,
            "recipient": lead.name
        })
        
        self.assertTrue(len(mcc) > 0, "Multi Channel Cadence was not spawned for the lead.")

    def test_evaluate_cadence_invalid_json(self):
        # Create a Cadence with invalid JSON assignment rule
        cadence_title = "Test Invalid JSON Cadence"
        existing = frappe.db.exists("Cadence", {"cadence_name": cadence_title})
        if not existing:
            cadence = frappe.get_doc({
                "doctype": "Cadence",
                "cadence_name": cadence_title,
                "assign_condition_json": "INVALID_JSON",
                "status": "Enabled"
            }).insert(ignore_permissions=True)
            cadence_name = cadence.name
        else:
            cadence_name = existing
            
        from frappe_cadence.cadence.doctype.cadence.cadence import evaluate_cadence_for_leads
        
        with patch("frappe_cadence.cadence.doctype.cadence.cadence.frappe.log_error") as mock_log_error:
            evaluate_cadence_for_leads(cadence_name)
            mock_log_error.assert_called_once()
            self.assertEqual(mock_log_error.call_args[1]["title"], "Invalid Cadence Assign Condition JSON")

    def test_evaluate_lead_invalid_json(self):
        # Create a Cadence with invalid JSON assignment rule
        cadence_title = "Test Invalid JSON Cadence 2"
        existing = frappe.db.exists("Cadence", {"cadence_name": cadence_title})
        if not existing:
            cadence = frappe.get_doc({
                "doctype": "Cadence",
                "cadence_name": cadence_title,
                "assign_condition_json": "INVALID_JSON",
                "status": "Enabled"
            }).insert(ignore_permissions=True)
            cadence_name = cadence.name
        else:
            cadence_name = existing
            
        lead = frappe.get_doc({
            "doctype": "CRM Lead",
            "first_name": "Test",
            "lead_name": "Test Invalid Lead"
        }).insert(ignore_permissions=True)
            
        from frappe_cadence.cadence.doctype.cadence.cadence import evaluate_lead_for_cadences
        
        with patch("frappe_cadence.cadence.doctype.cadence.cadence.frappe.log_error") as mock_log_error:
            evaluate_lead_for_cadences(lead.name)
            
            # evaluate_lead_for_cadences iterates over all cadences.
            # We just need to check if the error was logged for our invalid cadence.
            calls = mock_log_error.call_args_list
            self.assertTrue(any(call[1].get("title") == "Error evaluating Cadence assignment JSON" for call in calls))
