import frappe
from frappe.tests import IntegrationTestCase
from frappe_cadence.cadence.doctype.playbook_execution.playbook_execution import on_update

class TestPlaybookExecutionHandoff(IntegrationTestCase):
    def setUp(self):
        super().setUp()

    def tearDown(self):
        frappe.db.rollback()
        super().tearDown()

    def create_mock_playbook_execution(self, reference_doctype, reference_name, status="success"):
        class MockPlaybookExecution:
            def __init__(self, ref_doctype, ref_name, current_status):
                self.reference_doctype = ref_doctype
                self.reference_name = ref_name
                self.status = current_status
            
            def has_value_changed(self, field):
                # Always pretend it changed for the purpose of the test
                return True
                
        return MockPlaybookExecution(reference_doctype, reference_name, status)
    
    def create_mock_cadence(self):
        # Prevent errors from MCC on_update by providing a valid cadence
        cadence = frappe.get_doc({
            "doctype": "Cadence",
            "title": "Mock Cadence"
        }).insert(ignore_mandatory=True)
        return cadence.name

    def create_mock_recipient(self):
        lead = frappe.get_doc({
            "doctype": "CRM Lead",
            "first_name": "Test Lead"
        }).insert(ignore_mandatory=True)
        return lead.name

    def create_mock_mcc(self, status):
        return frappe.get_doc({
            "doctype": "Multi Channel Cadence",
            "title": "Test MCC",
            "status": status,
            "cadence_name": self.create_mock_cadence(),
            "recipient": self.create_mock_recipient(),
            "start_date": "2024-01-01"
        }).insert(ignore_mandatory=True)

    def test_playbook_execution_success_updates_mcc_to_draft(self):
        mcc = self.create_mock_mcc("Provisioning")
        
        # We test the on_update function directly, simulating the hook
        pe = self.create_mock_playbook_execution("Multi Channel Cadence", mcc.name, "success")
        
        on_update(pe, "on_update")
        
        mcc.reload()
        self.assertEqual(mcc.status, "Draft")

    def test_playbook_execution_error_updates_mcc_to_error(self):
        mcc = self.create_mock_mcc("Provisioning")
        
        pe = self.create_mock_playbook_execution("Multi Channel Cadence", mcc.name, "error")
        
        on_update(pe, "on_update")
        
        mcc.reload()
        self.assertEqual(mcc.status, "Error")

    def test_playbook_execution_ignores_mcc_not_in_provisioning(self):
        mcc = self.create_mock_mcc("In Progress")
        
        pe = self.create_mock_playbook_execution("Multi Channel Cadence", mcc.name, "success")
        
        on_update(pe, "on_update")
        
        mcc.reload()
        self.assertEqual(mcc.status, "In Progress")

    def test_playbook_execution_ignores_other_doctypes(self):
        # We simulate a completely different doctype
        pe = self.create_mock_playbook_execution("Other DocType", "Test1", "success")
        
        # Should not raise any errors
        on_update(pe, "on_update")
