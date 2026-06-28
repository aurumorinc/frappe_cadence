import frappe
from frappe.tests import IntegrationTestCase
from unittest.mock import patch, call
import json
from frappe_cadence.cadence.agent import process_cadence_step, callback

class TestAgentUtils(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.cadence_name = "TEST-MC-CADENCE-0001"
        cls.prev_schedule_name = "TEST-SCHEDULE-0000"
        
        frappe.conf.cadence_agent_base_url = "http://test.com"
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

        if not frappe.db.exists("Cadence", "_Test Master Cadence"):
            master = frappe.get_doc({
                "doctype": "Cadence",
                "cadence_name": "_Test Master Cadence",
                "cadence_schedules": [
                    {"reference_doctype": "Email Template", "reference_name": "Test Email Template", "send_after_days": 1}
                ]
            }).insert(ignore_permissions=True)
            cls.schedule_name = master.cadence_schedules[0].name
        else:
            master = frappe.get_doc("Cadence", "_Test Master Cadence")
            cls.schedule_name = master.cadence_schedules[0].name

        if not frappe.db.exists("Multi Channel Cadence", {"cadence_name": "_Test Master Cadence"}):
            camp = frappe.get_doc({
                "doctype": "Multi Channel Cadence",
                "cadence_name": "_Test Master Cadence",
                "cadence_for": "CRM Lead",
                "recipient": cls.lead_name,
                "start_date": "2024-01-01",
                "status": "Scheduled"
            }).insert(ignore_permissions=True)
            cls.cadence_name = camp.name
        else:
<<<<<<< ours:frappe_cadence/tests/integration/cadence/test_agent.py
            camp = frappe.get_all("Multi Channel Cadence", filters={"cadence_name": "_Test Master Cadence"}, limit=1)[0]
            cls.cadence_name = camp.name
||||||| ancestor
            camp = frappe.get_all("Multi Channel Campaign", filters={"campaign_name": "_Test Master Campaign"}, limit=1)[0]
            cls.campaign_name = camp.name
            
        frappe.db.commit()
=======
            camp = frappe.get_all("Multi Channel Campaign", filters={"campaign_name": "_Test Master Campaign"}, limit=1)[0]
            cls.campaign_name = camp.name
>>>>>>> theirs:frappe_campaign/campaign/test_agent.py

    @classmethod
    def tearDownClass(cls):
        frappe.db.rollback()
<<<<<<< ours:frappe_cadence/tests/integration/cadence/test_agent.py
        super().tearDownClass()

    def setUp(self):
        frappe.db.delete("Communication", {"reference_name": self.cadence_name})
        frappe.cache().delete_value(f"ai_req:{self.cadence_name}:{self.schedule_name}")
||||||| ancestor
        frappe.db.delete("Communication", {"reference_name": self.campaign_name})
        frappe.cache().delete_value(f"ai_req:{self.campaign_name}:{self.schedule_name}")
=======
        super().tearDownClass()

    def setUp(self):
        frappe.db.delete("Communication", {"reference_name": self.campaign_name})
        frappe.cache().delete_value(f"ai_req:{self.campaign_name}:{self.schedule_name}")
>>>>>>> theirs:frappe_campaign/campaign/test_agent.py
        
        frappe.conf["cadence_agent_base_url"] = "http://test.com"
        frappe.conf["cadence_agent_api_key"] = "test"
        frappe.conf["cadence_agent_webhook_secret"] = "test"

    @patch("frappe_cadence.cadence.agent.wait_for_event")
    def test_process_step_waits_for_previous_step(self, mock_wait):
        process_cadence_step(self.cadence_name, self.schedule_name, self.prev_schedule_name)
        mock_wait.assert_called_once_with(
            "cadence_step_completed",
            condition=f"argument.get('cadence_name') == '{self.cadence_name}' and argument.get('schedule_name') == '{self.prev_schedule_name}'"
        )

    @patch("frappe_cadence.cadence.agent.wait_for_event")
    @patch("frappe_cadence.cadence.agent.emit_event")
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
        with patch("frappe_cadence.cadence.agent.frappe.get_doc") as mock_get_doc:
            mock_schedule = frappe._dict(reference_doctype="Email Template", reference_name="Test Email Template")
            mock_template = frappe._dict(status="Enabled", subject="Test", message="Test Content")
            
            def side_effect(*args, **kwargs):
                dt = args[0] if args else kwargs.get("doctype")
                if dt == "Cadence Multi Channel Schedule": return mock_schedule
                if dt == "Email Template": return mock_template
                return original_get_doc(*args, **kwargs)
            mock_get_doc.side_effect = side_effect
            
            process_cadence_step(self.cadence_name, self.schedule_name, self.prev_schedule_name)
            
        mock_wait.assert_not_called()
        mock_emit.assert_called_once_with("cadence_step_completed", {"cadence_name": self.cadence_name, "schedule_name": self.schedule_name})

    @patch("frappe_cadence.cadence.agent.emit_event")
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

        process_cadence_step(self.cadence_name, self.schedule_name)
        mock_emit.assert_called_once_with("cadence_step_completed", {"cadence_name": self.cadence_name, "schedule_name": self.schedule_name})

    @patch("frappe_cadence.cadence.agent.emit_event")
    def test_process_step_enabled_template(self, mock_emit):
        original_get_doc = frappe.get_doc
        with patch("frappe_cadence.cadence.agent.frappe.get_doc") as mock_get_doc:
            mock_schedule = frappe._dict(reference_doctype="Email Template", reference_name="Test Email Template")
            mock_template = frappe._dict(status="Enabled", subject="Test", message="Test Content")
            
            def side_effect(*args, **kwargs):
                dt = args[0] if args else kwargs.get("doctype")
                if dt == "Cadence Multi Channel Schedule": return mock_schedule
                if dt == "Email Template": return mock_template
                return original_get_doc(*args, **kwargs)
            mock_get_doc.side_effect = side_effect
            
            process_cadence_step(self.cadence_name, self.schedule_name)
            
        comm = frappe.get_all("Communication", filters={"cadence_schedule": self.schedule_name})
        self.assertTrue(comm)
        mock_emit.assert_called_once_with("cadence_step_completed", {"cadence_name": self.cadence_name, "schedule_name": self.schedule_name})

    @patch("frappe_cadence.cadence.agent.requests.post")
    @patch("frappe_cadence.cadence.agent.wait_for_event")
    @patch.dict("frappe_cadence.cadence.agent.frappe.conf", {"cadence_agent_base_url": "http://test.com", "cadence_agent_api_key": "test", "cadence_agent_webhook_secret": "test"})
    def test_process_step_prompt_template_sends_webhook(self, mock_wait, mock_post):
        
        original_get_doc = frappe.get_doc
        with patch("frappe_cadence.cadence.agent.frappe.get_doc") as mock_get_doc:
            
            mock_schedule = frappe._dict(reference_doctype="Email Template", reference_name="Test Email Template")
            mock_template = frappe._dict(status="Prompt", subject="Test", system_prompt="Sys", user_prompt="User")
            mock_cadence = frappe._dict(cadence_for="CRM Lead", recipient=self.lead_name, name=self.cadence_name)
            mock_lead = frappe._dict(name=self.lead_name, organization=None)
            
            def side_effect(*args, **kwargs):
                dt = args[0] if args else kwargs.get("doctype")
                if dt == "Cadence Multi Channel Schedule": return mock_schedule
                if dt == "Email Template": return mock_template
                if dt == "Multi Channel Cadence": return mock_cadence
                if dt == "CRM Lead": return mock_lead
                return original_get_doc(*args, **kwargs)
            mock_get_doc.side_effect = side_effect
            
            process_cadence_step(self.cadence_name, self.schedule_name)
            
        mock_post.assert_called_once()
        mock_wait.assert_called_once()

    @patch("frappe_cadence.cadence.agent.requests.post")
    @patch("frappe_cadence.cadence.agent.wait_for_event")
    
    @patch("frappe.utils.redis_wrapper.RedisWrapper.get_value")
    def test_process_step_prompt_template_skips_webhook_if_cached(self, mock_get_value, mock_wait, mock_post):
        
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
        with patch("frappe_cadence.cadence.agent.frappe.get_doc") as mock_get_doc:
            
            mock_schedule = frappe._dict(reference_doctype="Email Template", reference_name="Test Email Template")
            mock_template = frappe._dict(status="Prompt", subject="Test", system_prompt="Sys", user_prompt="User")
            
            def side_effect(*args, **kwargs):
                dt = args[0] if args else kwargs.get("doctype")
                if dt == "Cadence Multi Channel Schedule": return mock_schedule
                if dt == "Email Template": return mock_template
                return original_get_doc(*args, **kwargs)
            mock_get_doc.side_effect = side_effect
            
            process_cadence_step(self.cadence_name, self.schedule_name)
            
        mock_post.assert_not_called()
        mock_wait.assert_called_once()

    @patch("frappe_cadence.cadence.agent.requests.post")
    @patch("frappe_cadence.cadence.agent.wait_for_event")
    
    def test_process_step_schema_generation_email(self, mock_wait, mock_post):
        
        original_get_doc = frappe.get_doc
        with patch("frappe_cadence.cadence.agent.frappe.get_doc") as mock_get_doc:
            
            mock_schedule = frappe._dict(reference_doctype="Email Template", reference_name="Test Email Template")
            mock_template = frappe._dict(status="Prompt", subject="Test", system_prompt="Sys", user_prompt="User")
            mock_cadence = frappe._dict(cadence_for="CRM Lead", recipient=self.lead_name, name=self.cadence_name)
            mock_lead = frappe._dict(name=self.lead_name, organization=None)
            
            def side_effect(*args, **kwargs):
                dt = args[0] if args else kwargs.get("doctype")
                if dt == "Cadence Multi Channel Schedule": return mock_schedule
                if dt == "Email Template": return mock_template
                if dt == "Multi Channel Cadence": return mock_cadence
                if dt == "CRM Lead": return mock_lead
                return original_get_doc(*args, **kwargs)
            mock_get_doc.side_effect = side_effect
            
            process_cadence_step(self.cadence_name, self.schedule_name)
            
        payload = json.loads(mock_post.call_args[1]["data"])
        schema = payload["response_format"]["json_schema"]["schema"]
        self.assertIn("subject", schema["properties"])
        self.assertIn("content", schema["properties"])
        self.assertIn("subject", schema["required"])
        self.assertIn("content", schema["required"])

    @patch("frappe_cadence.cadence.agent.requests.post")
    @patch("frappe_cadence.cadence.agent.wait_for_event")
    
    def test_process_step_schema_generation_non_email(self, mock_wait, mock_post):
        
        original_get_doc = frappe.get_doc
        with patch("frappe_cadence.cadence.agent.frappe.get_doc") as mock_get_doc:
            
            mock_schedule = frappe._dict(reference_doctype="LinkedIn Template", reference_name="Test LinkedIn Template")
            mock_template = frappe._dict(status="Prompt", system_prompt="Sys", user_prompt="User")
            mock_cadence = frappe._dict(cadence_for="CRM Lead", recipient=self.lead_name, name=self.cadence_name)
            mock_lead = frappe._dict(name=self.lead_name, organization=None)
            
            def side_effect(*args, **kwargs):
                dt = args[0] if args else kwargs.get("doctype")
                if dt == "Cadence Multi Channel Schedule": return mock_schedule
                if dt == "LinkedIn Template": return mock_template
                if dt == "Multi Channel Cadence": return mock_cadence
                if dt == "CRM Lead": return mock_lead
                return original_get_doc(*args, **kwargs)
            mock_get_doc.side_effect = side_effect
            
            process_cadence_step(self.cadence_name, self.schedule_name)
            
        payload = json.loads(mock_post.call_args[1]["data"])
        schema = payload["response_format"]["json_schema"]["schema"]
        self.assertNotIn("subject", schema["properties"])
        self.assertIn("content", schema["properties"])
        self.assertNotIn("subject", schema["required"])
        self.assertIn("content", schema["required"])

    @patch("frappe_cadence.cadence.agent.emit_event")
    def test_callback_creates_communication(self, mock_emit):
        comm = frappe.get_doc({
            "doctype": "Communication",
            "communication_medium": "Email",
            "subject": "Test",
            "reference_doctype": "Multi Channel Cadence",
            "reference_name": self.cadence_name,
            "cadence_schedule": self.schedule_name,
            "status": "Open"
        }).insert(ignore_permissions=True)

        payload = {
            "metadata": {"name": comm.name},
            "output": [{"content": [{"text": json.dumps({"subject": "AI Subject", "content": "AI Content"})}]}]
        }

        frappe.local.request = frappe._dict(json=payload)
        res = callback()
            
        self.assertEqual(res.get("status"), "success")
        
        comm.reload()
        self.assertEqual(comm.subject, "AI Subject")
        self.assertEqual(comm.content, "AI Content")
        self.assertEqual(comm.delivery_status, "Scheduled")
        
        mock_emit.assert_called_once_with("ai_agent_callback", {"communication_id": comm.name})
