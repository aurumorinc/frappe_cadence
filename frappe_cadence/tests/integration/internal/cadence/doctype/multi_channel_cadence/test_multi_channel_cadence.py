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
            
        cjt = frappe.db.exists("Controller Job Type", {"method": "frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.process_schedule"})
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
                "method": "frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.process_schedule"
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
    def test_on_update_enqueues_all_steps_initially(self, mock_enqueue):
        self.cadence.insert(ignore_permissions=True)
        mock_enqueue.reset_mock()
        self.cadence.on_update()
        
        self.assertEqual(mock_enqueue.call_count, 3)
        
        calls = [
            call("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.process_schedule", queue="medium", cadence_name=self.cadence.name, schedule_name=self.master_cadence.cadence_schedules[0].name, previous_schedule_name=None),
            call("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.process_schedule", queue="medium", cadence_name=self.cadence.name, schedule_name=self.master_cadence.cadence_schedules[1].name, previous_schedule_name=self.master_cadence.cadence_schedules[0].name),
            call("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.process_schedule", queue="medium", cadence_name=self.cadence.name, schedule_name=self.master_cadence.cadence_schedules[2].name, previous_schedule_name=self.master_cadence.cadence_schedules[1].name)
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
            call("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.process_schedule", queue="medium", cadence_name=self.cadence.name, schedule_name=self.master_cadence.cadence_schedules[1].name, previous_schedule_name=self.master_cadence.cadence_schedules[0].name),
            call("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.process_schedule", queue="medium", cadence_name=self.cadence.name, schedule_name=self.master_cadence.cadence_schedules[2].name, previous_schedule_name=self.master_cadence.cadence_schedules[1].name)
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
import frappe
from frappe.tests import IntegrationTestCase
from unittest.mock import patch, call, MagicMock
import json
from frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence import process_schedule

class TestAgentUtils(IntegrationTestCase):
    def tearDown(self):
        if hasattr(frappe, "_site_cached_load_app_hooks") and hasattr(frappe._site_cached_load_app_hooks, "clear_cache"):
            frappe._site_cached_load_app_hooks.clear_cache()
        if hasattr(frappe, "_request_cached_load_app_hooks") and hasattr(frappe._request_cached_load_app_hooks, "clear_cache"):
            frappe._request_cached_load_app_hooks.clear_cache()
        if hasattr(frappe.local, 'site_cache'):
            frappe.local.site_cache.clear()
        if hasattr(frappe.local, 'request_cache'):
            frappe.local.request_cache.clear()
        if hasattr(frappe, "client_cache") and hasattr(frappe.client_cache, "delete_value"):
            frappe.client_cache.delete_value("app_hooks")
        if hasattr(frappe, "cache") and hasattr(frappe.cache, "delete_value"):
            frappe.cache.delete_value("app_hooks")
        elif hasattr(frappe, "cache") and callable(frappe.cache):
            frappe.cache().delete_value("app_hooks")
        super().tearDown()

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.cadence_name = "TEST-MC-CADENCE-0001"
        cls.prev_schedule_name = "TEST-SCHEDULE-0000"
        
        
        if not frappe.db.exists("Sift Settings"):
            doc = frappe.new_doc("Sift Settings")
            doc.sift_base_url = "http://test.com"
            doc.sift_api_key = "test"
            doc.insert(ignore_permissions=True)
        else:
            doc = frappe.get_doc("Sift Settings")
            doc.sift_base_url = "http://test.com"
            doc.sift_api_key = "test"
            doc.save(ignore_permissions=True)

        frappe.conf.cadence_agent_api_key = "test"
        frappe.conf.cadence_agent_webhook_secret = "test"

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

        master_cadence_name = "_Test Master Cadence"
        existing_master = frappe.db.exists("Cadence", {"cadence_name": master_cadence_name})
        if not existing_master:
            master = frappe.get_doc({
                "doctype": "Cadence",
                "cadence_name": master_cadence_name,
                "cadence_schedules": [
                    {"reference_doctype": "Email Template", "reference_name": "Test Email Template", "send_after_days": 1}
                ]
            }).insert(ignore_permissions=True)
            cls.schedule_name = master.cadence_schedules[0].name
            master_name = master.name
        else:
            master = frappe.get_doc("Cadence", existing_master)
            cls.schedule_name = master.cadence_schedules[0].name
            master_name = master.name

        existing_camp = frappe.db.exists("Multi Channel Cadence", {"cadence_name": master_name})
        if not existing_camp:
            camp = frappe.get_doc({
                "doctype": "Multi Channel Cadence",
                "cadence_name": master_name,
                "cadence_for": "CRM Lead",
                "recipient": cls.lead_name,
                "start_date": "2024-01-01",
                "status": "Scheduled"
            }).insert(ignore_permissions=True)
            cls.cadence_name = camp.name
        else:
            camp = frappe.get_doc("Multi Channel Cadence", existing_camp)
            cls.cadence_name = camp.name
            
        cls.mcc = camp

    @classmethod
    def tearDownClass(cls):
        frappe.db.rollback()
        
        # Explicit teardown for hardcoded entities as a fallback
        frappe.db.delete("Multi Channel Cadence", {"cadence_name": "_Test Master Cadence"})
        frappe.db.delete("Cadence", {"cadence_name": "_Test Master Cadence"})
        
        super().tearDownClass()

    def setUp(self):
        frappe.db.delete("Communication", {"reference_name": self.cadence_name})
        frappe.cache().delete_value(f"ai_req:{self.cadence_name}:{self.schedule_name}")
        
        frappe.db.delete("User Bio", {"reference_user": self.mcc.owner})
        frappe.get_doc({
            "doctype": "User Bio",
            "reference_user": self.mcc.owner,
            "is_default": 1,
            "enabled": 1,
            "content": "<p>I am a <strong>bold</strong> user.</p>"
        }).insert(ignore_permissions=True)
        
        frappe.conf["cadence_agent_api_key"] = "test"
        frappe.conf["cadence_agent_webhook_secret"] = "test"

    @patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.wait_for_event")
    def test_process_step_waits_for_mcc_status(self, mock_wait):
        # Set MCC status to Draft
        frappe.db.set_value("Multi Channel Cadence", self.cadence_name, "status", "Draft")
        
        process_schedule(self.cadence_name, self.schedule_name, self.prev_schedule_name)
        
        mock_wait.assert_called_once_with(
            event_key="mcc_scheduled",
            condition=f"argument.get('doctype') == 'Multi Channel Cadence' and argument.get('name') == '{self.cadence_name}'"
        )
        
        # Restore status
        frappe.db.set_value("Multi Channel Cadence", self.cadence_name, "status", "Scheduled")

    @patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.emit_event")
    def test_on_update_emits_resume_event(self, mock_emit):
        # Set to Draft first
        frappe.db.set_value("Multi Channel Cadence", self.cadence_name, "status", "Draft")
        mcc = frappe.get_doc("Multi Channel Cadence", self.cadence_name)
        
        # Now save as Scheduled (resume)
        mcc.status = "Scheduled"
        mcc.save(ignore_permissions=True)
        
        # Assert event was emitted instead of enqueue
        mock_emit.assert_called_with("mcc_scheduled", {"doctype": "Multi Channel Cadence", "name": self.cadence_name})

    @patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.wait_for_event")
    def test_process_step_waits_for_previous_step(self, mock_wait):
        process_schedule(self.cadence_name, self.schedule_name, self.prev_schedule_name)
        mock_wait.assert_called_once_with(
            "cadence_step_completed",
            condition=f"argument.get('cadence_name') == '{self.cadence_name}' and argument.get('schedule_name') == '{self.prev_schedule_name}'"
        )

    @patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.wait_for_event")
    @patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.emit_event")
    def test_process_step_skips_wait_if_previous_step_done(self, mock_emit, mock_wait):
        # Create previous communication
        frappe.get_doc({
            "doctype": "Communication",
            "communication_medium": "Email",
            "subject": "Test",
            "reference_doctype": "Multi Channel Cadence",
            "reference_name": self.cadence_name,
            "cadence_schedule": self.prev_schedule_name,
            "delivery_status": "Sent"
        }).insert(ignore_permissions=True)

        original_get_doc = frappe.get_doc
        
        # Mock template
        with patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.frappe.get_doc") as mock_get_doc:
            mock_schedule = frappe._dict(reference_doctype="Email Template", reference_name="Test Email Template")
            mock_template = frappe._dict(status="Enabled", subject="Test", message="Test Content")
            
            def side_effect(*args, **kwargs):
                dt = args[0] if args else kwargs.get("doctype")
                if dt == "Cadence Multi Channel Schedule": return mock_schedule
                if dt == "Email Template": return mock_template
                return original_get_doc(*args, **kwargs)
            mock_get_doc.side_effect = side_effect
            
            process_schedule(self.cadence_name, self.schedule_name, self.prev_schedule_name)
            
        mock_wait.assert_not_called()
        mock_emit.assert_called_once_with("cadence_step_completed", {"cadence_name": self.cadence_name, "schedule_name": self.schedule_name})

    @patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.emit_event")
    def test_process_step_idempotency_returns_early(self, mock_emit):
        # Create current communication
        frappe.get_doc({
            "doctype": "Communication",
            "communication_medium": "Email",
            "subject": "Test",
            "reference_doctype": "Multi Channel Cadence",
            "reference_name": self.cadence_name,
            "cadence_schedule": self.schedule_name,
            "delivery_status": "Scheduled"
        }).insert(ignore_permissions=True)

        process_schedule(self.cadence_name, self.schedule_name)
        mock_emit.assert_called_once_with("cadence_step_completed", {"cadence_name": self.cadence_name, "schedule_name": self.schedule_name})

    @patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.wait_for_event")
    def test_process_step_waits_for_template_enabled(self, mock_wait):
        original_get_doc = frappe.get_doc
        with patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.frappe.get_doc") as mock_get_doc:
            mock_schedule = frappe._dict(reference_doctype="Email Template", reference_name="Test Email Template")
            mock_template = frappe._dict(status="Disabled", subject="Test", message="Test Content")
            mock_cadence = frappe._dict(owner=self.mcc.owner, cadence_for="CRM Lead", recipient=self.lead_name, name=self.cadence_name, sift_id="test_sift_id", status="Scheduled")
            
            def side_effect(*args, **kwargs):
                dt = args[0] if args else kwargs.get("doctype")
                if dt == "Cadence Multi Channel Schedule": return mock_schedule
                if dt == "Email Template": return mock_template
                if dt == "Multi Channel Cadence": return mock_cadence
                return original_get_doc(*args, **kwargs)
            mock_get_doc.side_effect = side_effect
            
            process_schedule(self.cadence_name, self.schedule_name)
            
        mock_wait.assert_called_once_with(
            event_key="email_template_enabled",
            condition=f"argument.get('doctype') == 'Email Template' and argument.get('name') == 'Test Email Template' and argument.get('enabled') == 1"
        )

    @patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.emit_event")
    def test_process_step_enabled_template(self, mock_emit):
        original_get_doc = frappe.get_doc
        with patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.frappe.get_doc") as mock_get_doc:
            mock_schedule = frappe._dict(reference_doctype="Email Template", reference_name="Test Email Template")
            mock_template = frappe._dict(status="Enabled", subject="Test", message="Test Content")
            
            def side_effect(*args, **kwargs):
                dt = args[0] if args else kwargs.get("doctype")
                if dt == "Cadence Multi Channel Schedule": return mock_schedule
                if dt == "Email Template": return mock_template
                return original_get_doc(*args, **kwargs)
            mock_get_doc.side_effect = side_effect
            
            process_schedule(self.cadence_name, self.schedule_name)
            
        comm = frappe.get_all("Communication", filters={"cadence_schedule": self.schedule_name})
        self.assertTrue(comm)
        mock_emit.assert_called_once_with("cadence_step_completed", {"cadence_name": self.cadence_name, "schedule_name": self.schedule_name})

    @patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.emit_event")
    @patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.wait_for_event")
    def test_end_to_end_wakeup_execution(self, mock_wait, mock_emit):
        original_get_doc = frappe.get_doc
        with patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.frappe.get_doc") as mock_get_doc:
            mock_schedule = frappe._dict(reference_doctype="Email Template", reference_name="Test Email Template")
            mock_template = frappe._dict(status="Disabled", subject="Test", message="Test Content")
            mock_cadence = frappe._dict(owner=self.mcc.owner, cadence_for="CRM Lead", recipient=self.lead_name, name=self.cadence_name, sift_id="test_sift_id", status="Scheduled")
            
            def side_effect(*args, **kwargs):
                dt = args[0] if args else kwargs.get("doctype")
                if dt == "Cadence Multi Channel Schedule": return mock_schedule
                if dt == "Email Template": return mock_template
                if dt == "Multi Channel Cadence": return mock_cadence
                return original_get_doc(*args, **kwargs)
            mock_get_doc.side_effect = side_effect
            
            # Step 1: Execution while Disabled
            process_schedule(self.cadence_name, self.schedule_name)
            
        mock_wait.assert_called_once()
        mock_emit.assert_not_called()
        
        # Step 2: Simulate Wakeup (Re-execution after status changed)
        mock_wait.reset_mock()
        with patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.frappe.get_doc") as mock_get_doc:
            mock_template_enabled = frappe._dict(status="Enabled", subject="Test", message="Test Content")
            
            def side_effect_enabled(*args, **kwargs):
                dt = args[0] if args else kwargs.get("doctype")
                if dt == "Cadence Multi Channel Schedule": return mock_schedule
                if dt == "Email Template": return mock_template_enabled
                if dt == "Multi Channel Cadence": return mock_cadence
                return original_get_doc(*args, **kwargs)
            mock_get_doc.side_effect = side_effect_enabled
            
            process_schedule(self.cadence_name, self.schedule_name)
            
        mock_wait.assert_not_called()
        comm = frappe.get_all("Communication", filters={"cadence_schedule": self.schedule_name})
        self.assertTrue(comm)
        mock_emit.assert_called_once_with("cadence_step_completed", {"cadence_name": self.cadence_name, "schedule_name": self.schedule_name})

    @patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.requests.post")
    @patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.wait_for_event")
    @patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.frappe.get_all")
    @patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.get_url")
    def test_process_step_prompt_template_sends_webhook(self, mock_get_url, mock_get_all, mock_wait, mock_post):
        mock_get_url.return_value = "http://test.com/webhook"
        
        def get_all_side_effect(doctype, *args, **kwargs):
            if doctype == "User Bio":
                return [frappe._dict(content="<p>I am a <strong>bold</strong> user.</p>")]
            return []
        mock_get_all.side_effect = get_all_side_effect
        
        original_get_doc = frappe.get_doc
        with patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.frappe.get_doc") as mock_get_doc:
            
            mock_schedule = frappe._dict(reference_doctype="Email Template", reference_name="Test Email Template")
            mock_template = frappe._dict(status="Prompt", subject="Test", annotations=[frappe._dict(input="")])
            mock_cadence = frappe._dict(owner=self.mcc.owner, cadence_for="CRM Lead", recipient=self.lead_name, name=self.cadence_name, sift_id="test_sift_id", status="Scheduled")
            mock_lead = frappe._dict(name=self.lead_name, organization=None)
            
            def side_effect(*args, **kwargs):
                dt = args[0] if args else kwargs.get("doctype")
                if dt == "Cadence Multi Channel Schedule": return mock_schedule
                if dt == "Email Template": return mock_template
                if dt == "Multi Channel Cadence": return mock_cadence
                if dt == "CRM Lead": return mock_lead
                return original_get_doc(*args, **kwargs)
            mock_get_doc.side_effect = side_effect
            
            process_schedule(self.cadence_name, self.schedule_name)
            
        mock_post.assert_called_once()
        mock_wait.assert_called_once()

    @patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.requests.post")
    @patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.wait_for_event")
    @patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.frappe.get_all")
    @patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.get_url")
    @patch("frappe.utils.redis_wrapper.RedisWrapper.get_value")
    def test_process_step_prompt_template_skips_webhook_if_cached(self, mock_get_value, mock_get_url, mock_get_all, mock_wait, mock_post):
        mock_get_url.return_value = "http://test.com/webhook"
        
        # Create draft communication
        comm = frappe.get_doc({
            "doctype": "Communication",
            "communication_medium": "Email",
            "subject": "Test",
            "reference_doctype": "Multi Channel Cadence",
            "reference_name": self.cadence_name,
            "cadence_schedule": self.schedule_name,
            "status": "Open"
        }).insert(ignore_permissions=True)
        
        def get_all_side_effect(doctype, *args, **kwargs):
            if doctype == "User Bio":
                return [frappe._dict(content="<p>I am a <strong>bold</strong> user.</p>")]
            if doctype == "Communication":
                # For idempotency check we return [], but for draft comm check we return [comm]
                if kwargs.get("filters", {}).get("delivery_status"):
                    return []
                return [frappe._dict(name=comm.name)]
            return []
        mock_get_all.side_effect = get_all_side_effect
        
        original_get_doc = frappe.get_doc
        with patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.frappe.get_doc") as mock_get_doc:
            
            mock_schedule = frappe._dict(reference_doctype="Email Template", reference_name="Test Email Template")
            mock_template = frappe._dict(status="Prompt", subject="Test", annotations=[frappe._dict(input="")])
            mock_cadence = frappe._dict(owner=self.mcc.owner, cadence_for="CRM Lead", recipient=self.lead_name, name=self.cadence_name, sift_id="test_sift_id", status="Scheduled")
            mock_lead = frappe._dict(name=self.lead_name, organization=None)
            
            def side_effect(*args, **kwargs):
                dt = args[0] if args else kwargs.get("doctype")
                if dt == "Cadence Multi Channel Schedule": return mock_schedule
                if dt == "Email Template": return mock_template
                if dt == "Multi Channel Cadence": return mock_cadence
                if dt == "CRM Lead": return mock_lead
                return original_get_doc(*args, **kwargs)
            mock_get_doc.side_effect = side_effect
            
            process_schedule(self.cadence_name, self.schedule_name)
            
        mock_post.assert_not_called()
        mock_wait.assert_called_once()

    @patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.wait_for_event")
    @patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.frappe.get_all")
    def test_process_step_missing_bio_yields(self, mock_get_all, mock_wait):
        def get_all_side_effect(doctype, *args, **kwargs):
            if doctype == "User Bio":
                return [] # Return empty bio
            return []
        mock_get_all.side_effect = get_all_side_effect
        
        # Create draft communication
        frappe.get_doc({
            "doctype": "Communication",
            "communication_medium": "Email",
            "subject": "Test",
            "reference_doctype": "Multi Channel Cadence",
            "reference_name": self.cadence_name,
            "cadence_schedule": self.schedule_name,
            "status": "Open"
        }).insert(ignore_permissions=True)
        
        original_get_doc = frappe.get_doc
        with patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.frappe.get_doc") as mock_get_doc:
            mock_schedule = frappe._dict(reference_doctype="Email Template", reference_name="Test Email Template")
            mock_template = frappe._dict(status="Prompt", subject="Test", annotations=[frappe._dict(input="")])
            mock_cadence = frappe._dict(owner=self.mcc.owner, cadence_for="CRM Lead", recipient=self.lead_name, name=self.cadence_name, sift_id="test_sift_id", status="Scheduled")
            mock_lead = frappe._dict(name=self.lead_name, organization=None)
            
            def side_effect(*args, **kwargs):
                dt = args[0] if args else kwargs.get("doctype")
                if dt == "Cadence Multi Channel Schedule": return mock_schedule
                if dt == "Email Template": return mock_template
                if dt == "Multi Channel Cadence": return mock_cadence
                if dt == "CRM Lead": return mock_lead
                return original_get_doc(*args, **kwargs)
            mock_get_doc.side_effect = side_effect
            
            with patch("frappe_cadence.cadence.doctype.user_bio.user_bio.get_user_bio", return_value=""):
                process_schedule(self.cadence_name, self.schedule_name)
            
        mock_wait.assert_called_once_with("user_bio_created", condition=f"argument.get('reference_user') == '{self.mcc.owner}'")

    @patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.frappe.log_error")
    @patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.requests.post")
    @patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.wait_for_event")
    @patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.frappe.get_all")
    @patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.get_url")
    def test_process_step_missing_sift_settings(self, mock_get_url, mock_get_all, mock_wait, mock_post, mock_log_error):
        mock_get_url.return_value = "http://test.com/webhook"
        
        def get_all_side_effect(doctype, *args, **kwargs):
            if doctype == "User Bio":
                return [frappe._dict(content="<p>I am a <strong>bold</strong> user.</p>")]
            return []
        mock_get_all.side_effect = get_all_side_effect
        
        # Create draft communication
        frappe.get_doc({
            "doctype": "Communication",
            "communication_medium": "Email",
            "subject": "Test",
            "reference_doctype": "Multi Channel Cadence",
            "reference_name": self.cadence_name,
            "cadence_schedule": self.schedule_name,
            "status": "Open"
        }).insert(ignore_permissions=True)
        
        # Clear Sift Settings temporarily
        settings = frappe.get_single("Sift Settings")
        settings.db_set("sift_base_url", None)
        
        original_get_doc = frappe.get_doc
        with patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.frappe.get_doc") as mock_get_doc:
            mock_schedule = frappe._dict(reference_doctype="Email Template", reference_name="Test Email Template")
            mock_template = frappe._dict(status="Prompt", subject="Test")
            mock_cadence = frappe._dict(owner=self.mcc.owner, cadence_for="CRM Lead", recipient=self.lead_name, name=self.cadence_name, sift_id="test_sift_id", status="Scheduled")
            mock_lead = frappe._dict(name=self.lead_name, organization=None)
            
            def side_effect(*args, **kwargs):
                dt = args[0] if args else kwargs.get("doctype")
                if dt == "Cadence Multi Channel Schedule": return mock_schedule
                if dt == "Email Template": return mock_template
                if dt == "Multi Channel Cadence": return mock_cadence
                if dt == "CRM Lead": return mock_lead
                return original_get_doc(*args, **kwargs)
            mock_get_doc.side_effect = side_effect
            
            process_schedule(self.cadence_name, self.schedule_name)
            
        mock_post.assert_not_called()
        mock_wait.assert_not_called()
        mock_log_error.assert_called_once_with(title="Sift Configuration Error", message="Sift Base URL not configured.")
        
        # Restore Sift Settings for other tests
        settings.db_set("sift_base_url", "http://test.com")

    @patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.requests.post")
    @patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.wait_for_event")
    @patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.frappe.get_all")
    @patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.get_url")
    def test_process_step_schema_generation_email(self, mock_get_url, mock_get_all, mock_wait, mock_post):
        mock_get_url.return_value = "http://test.com/webhook"
        
        def get_all_side_effect(doctype, *args, **kwargs):
            if doctype == "User Bio":
                return [frappe._dict(content="<p>I am a <strong>bold</strong> user.</p>")]
            return []
        mock_get_all.side_effect = get_all_side_effect
        
        original_get_doc = frappe.get_doc
        with patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.frappe.get_doc") as mock_get_doc:
            
            mock_schedule = frappe._dict(reference_doctype="Email Template", reference_name="Test Email Template")
            mock_template = frappe._dict(status="Prompt", subject="Test", annotations=[frappe._dict(input="")])
            mock_cadence = frappe._dict(owner=self.mcc.owner, cadence_for="CRM Lead", recipient=self.lead_name, name=self.cadence_name, sift_id="test_sift_id", status="Scheduled")
            mock_lead = frappe._dict(name=self.lead_name, organization=None)
            
            def side_effect(*args, **kwargs):
                dt = args[0] if args else kwargs.get("doctype")
                if dt == "Cadence Multi Channel Schedule": return mock_schedule
                if dt == "Email Template": return mock_template
                if dt == "Multi Channel Cadence": return mock_cadence
                if dt == "CRM Lead": return mock_lead
                return original_get_doc(*args, **kwargs)
            mock_get_doc.side_effect = side_effect
            
            process_schedule(self.cadence_name, self.schedule_name)
            
        payload = json.loads(mock_post.call_args[1]["data"])
        schema = payload["response_format"]["json_schema"]["schema"]
        self.assertIn("subject", schema["properties"])
        self.assertIn("content", schema["properties"])
        self.assertIn("subject", schema["required"])
        self.assertIn("content", schema["required"])

    @patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.requests.post")
    @patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.wait_for_event")
    @patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.frappe.get_all")
    @patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.get_url")
    def test_process_step_webhook_retry_on_cache_expire(self, mock_get_url, mock_get_all, mock_wait, mock_post):
        mock_get_url.return_value = "http://test.com/webhook"
        
        def get_all_side_effect(doctype, *args, **kwargs):
            if doctype == "User Bio":
                return [frappe._dict(content="<p>I am a <strong>bold</strong> user.</p>")]
            return []
        mock_get_all.side_effect = get_all_side_effect
        
        # Create draft communication
        frappe.get_doc({
            "doctype": "Communication",
            "communication_medium": "Email",
            "subject": "Test",
            "reference_doctype": "Multi Channel Cadence",
            "reference_name": self.cadence_name,
            "cadence_schedule": self.schedule_name,
            "status": "Open"
        }).insert(ignore_permissions=True)
        
        # Ensure cache is deleted (simulate expiry)
        frappe.cache().delete_value(f"ai_req:{self.cadence_name}:{self.schedule_name}")
        
        original_get_doc = frappe.get_doc
        with patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.frappe.get_doc") as mock_get_doc:
            mock_schedule = frappe._dict(reference_doctype="Email Template", reference_name="Test Email Template")
            mock_template = frappe._dict(status="Prompt", subject="Test", annotations=[frappe._dict(input="")])
            mock_cadence = frappe._dict(owner=self.mcc.owner, cadence_for="CRM Lead", recipient=self.lead_name, name=self.cadence_name, sift_id="test_sift_id", status="Scheduled")
            mock_lead = frappe._dict(name=self.lead_name, organization=None)
            
            def side_effect(*args, **kwargs):
                dt = args[0] if args else kwargs.get("doctype")
                if dt == "Cadence Multi Channel Schedule": return mock_schedule
                if dt == "Email Template": return mock_template
                if dt == "Multi Channel Cadence": return mock_cadence
                if dt == "CRM Lead": return mock_lead
                return original_get_doc(*args, **kwargs)
            mock_get_doc.side_effect = side_effect
            
            process_schedule(self.cadence_name, self.schedule_name)
            
        # Post should be called again since cache expired
        mock_post.assert_called_once()
        mock_wait.assert_called_once()

    @patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.requests.post")
    @patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.wait_for_event")
    @patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.frappe.get_all")
    @patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.get_url")
    @patch("frappe.model.document.Document.insert")
    def test_process_step_schema_generation_non_email(self, mock_insert, mock_get_url, mock_get_all, mock_wait, mock_post):
        mock_get_url.return_value = "http://test.com/webhook"
        mock_insert.return_value = MagicMock()
        
        def get_all_side_effect(doctype, *args, **kwargs):
            if doctype == "User Bio":
                return [frappe._dict(content="<p>I am a <strong>bold</strong> user.</p>")]
            if doctype == "Communication":
                return []
            if doctype == "History":
                return []
            if doctype == "Field":
                return []
            return []
        mock_get_all.side_effect = get_all_side_effect
        
        original_get_doc = frappe.get_doc
        with patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.frappe.get_doc") as mock_get_doc:
            
            mock_schedule = frappe._dict(reference_doctype="LinkedIn Template", reference_name="Test LinkedIn Template")
            mock_template = frappe._dict(status="Prompt", annotations=[frappe._dict(input="")])
            mock_cadence = frappe._dict(cadence_for="CRM Lead", recipient=self.lead_name, name=self.cadence_name, sift_id="test_sift_id", status="Scheduled")
            mock_lead = frappe._dict(name=self.lead_name, organization=None)
            
            def side_effect(*args, **kwargs):
                dt = args[0] if args else kwargs.get("doctype")
                if dt == "Cadence Multi Channel Schedule": return mock_schedule
                if dt == "LinkedIn Template": return mock_template
                if dt == "Multi Channel Cadence": return mock_cadence
                if dt == "CRM Lead": return mock_lead
                return original_get_doc(*args, **kwargs)
            mock_get_doc.side_effect = side_effect
            
            process_schedule(self.cadence_name, self.schedule_name)
            
        payload = json.loads(mock_post.call_args[1]["data"])
        schema = payload["response_format"]["json_schema"]["schema"]
        self.assertNotIn("subject", schema["properties"])
        self.assertIn("content", schema["properties"])
        self.assertNotIn("subject", schema["required"])
        self.assertIn("content", schema["required"])

    @patch("frappe_cadence.cadence.doctype.history.history.get_history")
    @patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.requests.post")
    @patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.wait_for_event")
    @patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.frappe.get_all")
    @patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.get_url")
    def test_process_step_multimodal_payload_construction(self, mock_get_url, mock_get_all, mock_wait, mock_post, mock_get_history):
        mock_get_url.return_value = "http://test.com/webhook"
        import os
        
        # 1. Create a real File record pointing to a local file
        test_file_path = "test_image_for_sift.png"
        with open(frappe.get_site_path("public", "files", test_file_path), "wb") as f:
            f.write(b"fake image data")
            
        file_doc = frappe._dict(
            file_name=test_file_path,
            is_private=1,
            file_url="/private/files/test_image_for_sift.png",
            presigned_url="https://s3.example.com/test_image_for_sift.png?sig=123"
        )

        def get_all_side_effect(doctype, *args, **kwargs):
            if doctype == "User Bio":
                return [frappe._dict(content="<p>I am a <strong>bold</strong> user.</p>")]
            if doctype == "Communication":
                return []
            return []
        mock_get_all.side_effect = get_all_side_effect
        
        original_get_doc = frappe.get_doc
        
        mock_get_history.return_value = [{"role": "user", "content": [{"type": "text", "text": "A very important email."}, {"type": "image_url", "image_url": {"url": "https://s3.example.com/test_image_for_sift.png?sig=123"}}]}]
        
        with patch("frappe_cadence.cadence.doctype.user_bio.user_bio.get_user_bio", return_value="<p>I am a <strong>bold</strong> user.</p>"):
            with patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.frappe.get_doc") as mock_get_doc:
                mock_schedule = frappe._dict(reference_doctype="Email Template", reference_name="Test Email Template")
                mock_template = frappe._dict(status="Prompt", annotations=[frappe._dict(input="")])
                mock_cadence = frappe._dict(cadence_for="CRM Lead", recipient=self.lead_name, name=self.cadence_name, sift_id="test_model_123", owner="user@test.com", status="Scheduled")
                mock_lead = frappe._dict(name=self.lead_name, organization=None)
                
                def side_effect(*args, **kwargs):
                    dt = args[0] if args else kwargs.get("doctype")
                    if dt == "Cadence Multi Channel Schedule": return mock_schedule
                    if dt == "Email Template": return mock_template
                    if dt == "Multi Channel Cadence": return mock_cadence
                    if dt == "CRM Lead": return mock_lead
                    if dt == "File": return file_doc
                    return original_get_doc(*args, **kwargs)
                mock_get_doc.side_effect = side_effect
                
                process_schedule(self.cadence_name, self.schedule_name)
            
        payload = json.loads(mock_post.call_args[1]["data"])
        
        # Assertions for payload format
        self.assertEqual(payload["model"], "test_model_123")
        self.assertEqual(payload["input"][0]["role"], "system")
        self.assertIn("I am a **bold** user.", payload["input"][0]["content"])
        
        history_msg = payload["input"][1]
        self.assertEqual(history_msg["role"], "user")
        self.assertEqual(history_msg["content"][0]["type"], "text")
        self.assertEqual(history_msg["content"][0]["text"], "A very important email.")
        
        self.assertEqual(history_msg["content"][1]["type"], "image_url")
        self.assertTrue(history_msg["content"][1]["image_url"]["url"].startswith("http"))
        self.assertIn("?sig=", history_msg["content"][1]["image_url"]["url"]) # Ensure presigned URL
        
        import os
        if os.path.exists(frappe.get_site_path("public", "files", test_file_path)):
            os.remove(frappe.get_site_path("public", "files", test_file_path))

