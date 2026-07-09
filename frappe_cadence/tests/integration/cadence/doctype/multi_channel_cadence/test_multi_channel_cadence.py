import frappe
from frappe.tests import IntegrationTestCase
from unittest.mock import patch, call
import json

class TestMultiChannelCadence(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Create necessary doctypes if they don't exist for testing
        if not frappe.db.exists("DocType", "FS Job"):
            doc = frappe.get_doc({
                "doctype": "DocType",
                "name": "FS Job",
                "module": "Core",
                "custom": 1,
                "fields": [
                    {"fieldname": "status", "fieldtype": "Data", "label": "Status"},
                    {"fieldname": "arguments", "fieldtype": "Code", "label": "Arguments"},
                    {"fieldname": "job_type", "fieldtype": "Data", "label": "Job Type"}
                ]
            })
            doc.insert(ignore_permissions=True)
            
        cjt = frappe.db.exists("Controller Job Type", {"method": "frappe_cadence.cadence.multi_channel_cadence.process_cadence_step"})
        if not cjt:
            if not frappe.db.exists("DocType", "Controller Job Type"):
                doc = frappe.get_doc({
                    "doctype": "DocType",
                    "name": "Controller Job Type",
                    "module": "Core",
                    "custom": 1,
                    "fields": [
                        {"fieldname": "method", "fieldtype": "Data", "label": "Method"}
                    ]
                })
                doc.insert(ignore_permissions=True)
            
            doc = frappe.get_doc({
                "doctype": "Controller Job Type",
                "method": "frappe_cadence.cadence.multi_channel_cadence.process_cadence_step"
            }).insert(ignore_permissions=True)
            cls.cjt_name = doc.name
        else:
            cls.cjt_name = cjt
            
        # Create templates
        for dt in ["Email Template", "LinkedIn Template", "SMS Template"]:
            name = f"Test {dt}"
            if not frappe.db.exists(dt, name):
                if dt == "Email Template":
                    doc = frappe.get_doc({
                        "doctype": dt,
                        "name": name,
                        "subject": "Test Subject",
                        "response": "Test Content",
                        "status": "Enabled"
                    })
                else:
                    doc = frappe.get_doc({
                        "doctype": dt,
                        "name": name,
                        "title": name,
                        "status": "Enabled"
                    })
                doc.insert(ignore_permissions=True)
                
        lead = frappe.get_all("CRM Lead", limit=1)
        if not lead:
            lead_doc = frappe.get_doc({
                "doctype": "CRM Lead",
                "first_name": "Test",
                "last_name": "Lead"
            }).insert(ignore_permissions=True)
            cls.lead_name = lead_doc.name
        else:
            cls.lead_name = lead[0].name

        # Create a master Cadence
        if not frappe.db.exists("Cadence", "_Test Master Cadence"):
            cls.master_cadence = frappe.get_doc({
                "doctype": "Cadence",
                "cadence_name": "_Test Master Cadence",
                "cadence_schedules": [
                    {"reference_doctype": "Email Template", "reference_name": "Test Email Template", "send_after_days": 1},
                    {"reference_doctype": "LinkedIn Template", "reference_name": "Test LinkedIn Template", "send_after_days": 2},
                    {"reference_doctype": "SMS Template", "reference_name": "Test SMS Template", "send_after_days": 3}
                ]
            }).insert(ignore_permissions=True)
        else:
            cls.master_cadence = frappe.get_doc("Cadence", "_Test Master Cadence")

    @classmethod
    def tearDownClass(cls):
        frappe.db.rollback()
        
        # Explicit teardown for hardcoded entities as a fallback
        frappe.db.delete("Multi Channel Cadence", {"cadence_name": "_Test Master Cadence"})
        frappe.db.delete("Cadence", {"cadence_name": "_Test Master Cadence"})
        frappe.db.delete("Communication", {"reference_doctype": "Multi Channel Cadence", "reference_name": "_Test Master Cadence"})
        
        super().tearDownClass()

    def setUp(self):
        # Create a dummy cadence
        self.cadence = frappe.get_doc({
            "doctype": "Multi Channel Cadence",
            "cadence_name": self.master_cadence.name,
            "cadence_for": "CRM Lead",
            "recipient": self.lead_name,
            "start_date": "2024-01-01",
            "status": "Scheduled"
        })

    def tearDown(self):
        if self.cadence.name:
            frappe.delete_doc("Multi Channel Cadence", self.cadence.name, ignore_permissions=True, force=True)

    @patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.enqueue")
    def test_on_update_cancels_existing_jobs(self, mock_enqueue):
        self.cadence.insert(ignore_permissions=True)
        mock_enqueue.reset_mock()
        
        # Create dummy FS Jobs
        job1 = frappe.get_doc({
            "doctype": "FS Job",
            "status": "queued",
            "job_type": self.cjt_name,
            "arguments": json.dumps({"cadence_name": self.cadence.name})
        }).insert(ignore_permissions=True)
        
        job2 = frappe.get_doc({
            "doctype": "FS Job",
            "status": "started",
            "job_type": self.cjt_name,
            "arguments": json.dumps({"cadence_name": self.cadence.name})
        }).insert(ignore_permissions=True)
        
        # Trigger on_update
        self.cadence.on_update()
        
        # Assert jobs are cancelled
        self.assertEqual(frappe.db.get_value("FS Job", job1.name, "status"), "canceled")
        self.assertEqual(frappe.db.get_value("FS Job", job2.name, "status"), "canceled")

    @patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.enqueue")
    def test_on_update_enqueues_all_steps_initially(self, mock_enqueue):
        self.cadence.insert(ignore_permissions=True)
        mock_enqueue.reset_mock()
        self.cadence.on_update()
        
        self.assertEqual(mock_enqueue.call_count, 3)
        
        calls = [
            call("frappe_cadence.cadence.multi_channel_cadence.process_cadence_step", queue="default", cadence_name=self.cadence.name, schedule_name=self.master_cadence.cadence_schedules[0].name, previous_schedule_name=None, now=True),
            call("frappe_cadence.cadence.multi_channel_cadence.process_cadence_step", queue="default", cadence_name=self.cadence.name, schedule_name=self.master_cadence.cadence_schedules[1].name, previous_schedule_name=self.master_cadence.cadence_schedules[0].name, now=True),
            call("frappe_cadence.cadence.multi_channel_cadence.process_cadence_step", queue="default", cadence_name=self.cadence.name, schedule_name=self.master_cadence.cadence_schedules[2].name, previous_schedule_name=self.master_cadence.cadence_schedules[1].name, now=True)
        ]
        mock_enqueue.assert_has_calls(calls)

    @patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.enqueue")
    def test_on_update_skips_sent_communications(self, mock_enqueue):
        self.cadence.insert(ignore_permissions=True)
        mock_enqueue.reset_mock()
        
        # Create a Sent Communication for schedule 1
        frappe.get_doc({
            "doctype": "Communication",
            "communication_medium": "Email",
            "subject": "Test",
            "reference_doctype": "Multi Channel Cadence",
            "reference_name": self.cadence.name,
            "cadence_schedule": self.master_cadence.cadence_schedules[0].name,
            "delivery_status": "Sent"
        }).insert(ignore_permissions=True)
        
        self.cadence.on_update()
        
        # Should only enqueue for schedule 2 and 3
        self.assertEqual(mock_enqueue.call_count, 2)
        
        calls = [
            call("frappe_cadence.cadence.multi_channel_cadence.process_cadence_step", queue="default", cadence_name=self.cadence.name, schedule_name=self.master_cadence.cadence_schedules[1].name, previous_schedule_name=self.master_cadence.cadence_schedules[0].name, now=True),
            call("frappe_cadence.cadence.multi_channel_cadence.process_cadence_step", queue="default", cadence_name=self.cadence.name, schedule_name=self.master_cadence.cadence_schedules[2].name, previous_schedule_name=self.master_cadence.cadence_schedules[1].name, now=True)
        ]
        mock_enqueue.assert_has_calls(calls)

    @patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.enqueue")
    def test_on_update_deletes_unsent_communications_and_requeues(self, mock_enqueue):
        self.cadence.insert(ignore_permissions=True)
        mock_enqueue.reset_mock()
        
        # Create a Scheduled Communication for schedule 1
        comm = frappe.get_doc({
            "doctype": "Communication",
            "communication_medium": "Email",
            "subject": "Test",
            "reference_doctype": "Multi Channel Cadence",
            "reference_name": self.cadence.name,
            "cadence_schedule": self.master_cadence.cadence_schedules[0].name,
            "delivery_status": "Scheduled"
        }).insert(ignore_permissions=True)
        
        self.cadence.on_update()
        
        # Assert Communication is deleted
        self.assertFalse(frappe.db.exists("Communication", comm.name))
        
        # Should enqueue for all 3 schedules
        self.assertEqual(mock_enqueue.call_count, 3)
