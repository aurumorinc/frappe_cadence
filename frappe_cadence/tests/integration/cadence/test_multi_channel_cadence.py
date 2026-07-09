import frappe
from frappe.tests import IntegrationTestCase
from unittest.mock import patch, call
import json
from frappe_cadence.cadence.multi_channel_cadence import process_cadence_step

class TestAgentUtils(IntegrationTestCase):
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
        
        
        frappe.conf["cadence_agent_api_key"] = "test"
        frappe.conf["cadence_agent_webhook_secret"] = "test"

    @patch("frappe_cadence.cadence.multi_channel_cadence.wait_for_event")
    def test_process_step_waits_for_previous_step(self, mock_wait):
        process_cadence_step(self.cadence_name, self.schedule_name, self.prev_schedule_name)
        mock_wait.assert_called_once_with(
            "cadence_step_completed",
            condition=f"argument.get('cadence_name') == '{self.cadence_name}' and argument.get('schedule_name') == '{self.prev_schedule_name}'"
        )

    @patch("frappe_cadence.cadence.multi_channel_cadence.wait_for_event")
    @patch("frappe_cadence.cadence.multi_channel_cadence.emit_event")
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
        with patch("frappe_cadence.cadence.multi_channel_cadence.frappe.get_doc") as mock_get_doc:
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

    @patch("frappe_cadence.cadence.multi_channel_cadence.emit_event")
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

    @patch("frappe_cadence.cadence.multi_channel_cadence.emit_event")
    def test_process_step_enabled_template(self, mock_emit):
        original_get_doc = frappe.get_doc
        with patch("frappe_cadence.cadence.multi_channel_cadence.frappe.get_doc") as mock_get_doc:
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

    @patch("frappe_cadence.cadence.multi_channel_cadence.requests.post")
    @patch("frappe_cadence.cadence.multi_channel_cadence.wait_for_event")
    @patch("frappe_cadence.cadence.multi_channel_cadence.frappe.get_all")
    @patch("frappe_cadence.cadence.multi_channel_cadence.get_url")
    def test_process_step_prompt_template_sends_webhook(self, mock_get_url, mock_get_all, mock_wait, mock_post):
        mock_get_url.return_value = "http://test.com/webhook"
        
        def get_all_side_effect(doctype, *args, **kwargs):
            return []
        mock_get_all.side_effect = get_all_side_effect
        
        original_get_doc = frappe.get_doc
        with patch("frappe_cadence.cadence.multi_channel_cadence.frappe.get_doc") as mock_get_doc:
            
            mock_schedule = frappe._dict(reference_doctype="Email Template", reference_name="Test Email Template")
            mock_template = frappe._dict(status="Prompt", subject="Test", annotations=[frappe._dict(input="")])
            mock_cadence = frappe._dict(cadence_for="CRM Lead", recipient=self.lead_name, name=self.cadence_name, sift_id="test_sift_id")
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

    @patch("frappe_cadence.cadence.multi_channel_cadence.requests.post")
    @patch("frappe_cadence.cadence.multi_channel_cadence.wait_for_event")
    @patch("frappe_cadence.cadence.multi_channel_cadence.frappe.get_all")
    @patch("frappe_cadence.cadence.multi_channel_cadence.get_url")
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
            if doctype == "Communication":
                # For idempotency check we return [], but for draft comm check we return [comm]
                if kwargs.get("filters", {}).get("delivery_status"):
                    return []
                return [frappe._dict(name=comm.name)]
            return []
        mock_get_all.side_effect = get_all_side_effect
        
        original_get_doc = frappe.get_doc
        with patch("frappe_cadence.cadence.multi_channel_cadence.frappe.get_doc") as mock_get_doc:
            
            mock_schedule = frappe._dict(reference_doctype="Email Template", reference_name="Test Email Template")
            mock_template = frappe._dict(status="Prompt", subject="Test", annotations=[frappe._dict(input="")])
            mock_cadence = frappe._dict(cadence_for="CRM Lead", recipient=self.lead_name, name=self.cadence_name, sift_id="test_sift_id")
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
            
        mock_post.assert_not_called()
        mock_wait.assert_called_once()

    @patch("frappe_cadence.cadence.multi_channel_cadence.frappe.log_error")
    @patch("frappe_cadence.cadence.multi_channel_cadence.requests.post")
    @patch("frappe_cadence.cadence.multi_channel_cadence.wait_for_event")
    @patch("frappe_cadence.cadence.multi_channel_cadence.frappe.get_all")
    @patch("frappe_cadence.cadence.multi_channel_cadence.get_url")
    def test_process_step_missing_sift_settings(self, mock_get_url, mock_get_all, mock_wait, mock_post, mock_log_error):
        mock_get_url.return_value = "http://test.com/webhook"
        
        def get_all_side_effect(doctype, *args, **kwargs):
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
        with patch("frappe_cadence.cadence.multi_channel_cadence.frappe.get_doc") as mock_get_doc:
            mock_schedule = frappe._dict(reference_doctype="Email Template", reference_name="Test Email Template")
            mock_template = frappe._dict(status="Prompt", subject="Test")
            mock_cadence = frappe._dict(cadence_for="CRM Lead", recipient=self.lead_name, name=self.cadence_name, sift_id="test_sift_id")
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
            
        mock_post.assert_not_called()
        mock_wait.assert_not_called()
        mock_log_error.assert_called_once_with(title="Sift Configuration Error", message="Sift Base URL not configured.")
        
        # Restore Sift Settings for other tests
        settings.db_set("sift_base_url", "http://test.com")

    @patch("frappe_cadence.cadence.multi_channel_cadence.requests.post")
    @patch("frappe_cadence.cadence.multi_channel_cadence.wait_for_event")
    @patch("frappe_cadence.cadence.multi_channel_cadence.frappe.get_all")
    @patch("frappe_cadence.cadence.multi_channel_cadence.get_url")
    def test_process_step_schema_generation_email(self, mock_get_url, mock_get_all, mock_wait, mock_post):
        mock_get_url.return_value = "http://test.com/webhook"
        
        def get_all_side_effect(doctype, *args, **kwargs):
            return []
        mock_get_all.side_effect = get_all_side_effect
        
        original_get_doc = frappe.get_doc
        with patch("frappe_cadence.cadence.multi_channel_cadence.frappe.get_doc") as mock_get_doc:
            
            mock_schedule = frappe._dict(reference_doctype="Email Template", reference_name="Test Email Template")
            mock_template = frappe._dict(status="Prompt", subject="Test", annotations=[frappe._dict(input="")])
            mock_cadence = frappe._dict(cadence_for="CRM Lead", recipient=self.lead_name, name=self.cadence_name, sift_id="test_sift_id")
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

    @patch("frappe_cadence.cadence.multi_channel_cadence.requests.post")
    @patch("frappe_cadence.cadence.multi_channel_cadence.wait_for_event")
    @patch("frappe_cadence.cadence.multi_channel_cadence.frappe.get_all")
    @patch("frappe_cadence.cadence.multi_channel_cadence.get_url")
    def test_process_step_webhook_retry_on_cache_expire(self, mock_get_url, mock_get_all, mock_wait, mock_post):
        mock_get_url.return_value = "http://test.com/webhook"
        
        def get_all_side_effect(doctype, *args, **kwargs):
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
        with patch("frappe_cadence.cadence.multi_channel_cadence.frappe.get_doc") as mock_get_doc:
            mock_schedule = frappe._dict(reference_doctype="Email Template", reference_name="Test Email Template")
            mock_template = frappe._dict(status="Prompt", subject="Test", annotations=[frappe._dict(input="")])
            mock_cadence = frappe._dict(cadence_for="CRM Lead", recipient=self.lead_name, name=self.cadence_name, sift_id="test_sift_id")
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
            
        # Post should be called again since cache expired
        mock_post.assert_called_once()
        mock_wait.assert_called_once()

    @patch("frappe_cadence.cadence.multi_channel_cadence.requests.post")
    @patch("frappe_cadence.cadence.multi_channel_cadence.wait_for_event")
    @patch("frappe_cadence.cadence.multi_channel_cadence.frappe.get_all")
    @patch("frappe_cadence.cadence.multi_channel_cadence.get_url")
    def test_process_step_schema_generation_non_email(self, mock_get_url, mock_get_all, mock_wait, mock_post):
        mock_get_url.return_value = "http://test.com/webhook"
        
        def get_all_side_effect(doctype, *args, **kwargs):
            if doctype == "Communication":
                return []
            if doctype == "History":
                return []
            if doctype == "History Image":
                return []
            return frappe.get_all(doctype, *args, **kwargs)
        mock_get_all.side_effect = get_all_side_effect
        
        original_get_doc = frappe.get_doc
        with patch("frappe_cadence.cadence.multi_channel_cadence.frappe.get_doc") as mock_get_doc:
            
            mock_schedule = frappe._dict(reference_doctype="LinkedIn Template", reference_name="Test LinkedIn Template")
            mock_template = frappe._dict(status="Prompt", annotations=[frappe._dict(input="")])
            mock_cadence = frappe._dict(cadence_for="CRM Lead", recipient=self.lead_name, name=self.cadence_name, sift_id="test_sift_id")
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

    @patch("frappe_cadence.cadence.multi_channel_cadence.requests.post")
    @patch("frappe_cadence.cadence.multi_channel_cadence.wait_for_event")
    @patch("frappe_cadence.cadence.multi_channel_cadence.frappe.get_all")
    @patch("frappe_cadence.cadence.multi_channel_cadence.get_url")
    def test_process_step_multimodal_payload_construction(self, mock_get_url, mock_get_all, mock_wait, mock_post):
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
            if doctype == "Communication":
                return []
            if doctype == "History":
                return [frappe._dict(name="HIST-001", content="A very important email.")]
            if doctype == "History Image":
                return [frappe._dict(image="/private/files/test_image_for_sift.png")]
            return []
        mock_get_all.side_effect = get_all_side_effect
        
        original_get_doc = frappe.get_doc
        
        original_get_value = frappe.db.get_value
        def get_value_side_effect(*args, **kwargs):
            doctype = kwargs.get("doctype") or (args[0] if len(args) > 0 else None)
            fieldname = kwargs.get("fieldname") or (args[2] if len(args) > 2 else None)
            if doctype == "User" and isinstance(fieldname, list) and "bio" in fieldname:
                return frappe._dict(name="user@test.com", full_name="Test User", bio="<p>I am a <strong>bold</strong> user.</p>")
            return original_get_value(*args, **kwargs)
            
        with patch.object(frappe.db, "get_value", side_effect=get_value_side_effect):
            with patch("frappe_cadence.cadence.multi_channel_cadence.frappe.get_doc") as mock_get_doc:
                mock_schedule = frappe._dict(reference_doctype="Email Template", reference_name="Test Email Template")
                mock_template = frappe._dict(status="Prompt", annotations=[frappe._dict(input="")])
                mock_cadence = frappe._dict(cadence_for="CRM Lead", recipient=self.lead_name, name=self.cadence_name, sift_id="test_model_123")
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
                
                process_cadence_step(self.cadence_name, self.schedule_name)
            
        payload = json.loads(mock_post.call_args[1]["data"])
        
        # Assertions for payload format
        self.assertEqual(payload["model"], "test_model_123")
        self.assertEqual(payload["input"][0]["role"], "system")
        self.assertIn("Test User", payload["input"][0]["content"])
        
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

