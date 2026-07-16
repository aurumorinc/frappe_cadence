import unittest
from unittest.mock import patch, MagicMock
import frappe
from frappe.tests import UnitTestCase

class MockMultiChannelCadence:
    def __init__(self):
        self.name = "MCC-001"
        self.cadence_name = "Test Cadence"
        self.recipient = "test@example.com"
        self.provider = []
        self.status = "Draft"
        self.flags = {}
        
    def append(self, key, value):
        if key == "provider":
            row = MagicMock()
            row.channel = value.get("channel")
            row.cadence_provider = value.get("cadence_provider")
            self.provider.append(row)

    def get(self, key, default=None):
        if key == "provider":
            return self.provider
        return default

    def has_value_changed(self, key):
        return True
        
    def get_doc_before_save(self):
        m = MagicMock()
        m.status = "Draft"
        return m

class TestMultiChannelCadence(UnitTestCase):

    @patch("frappe_cadence.cadence.doctype.cadence_provider.cadence_provider.resolve_providers_for_mcc")
    def test_mcc_initialization_provider_snapshot(self, mock_resolve):
        from frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence import MultiChannelCadence
        
        # Setup mock
        mock_resolve.return_value = {
            "Email": "Apollo",
            "LinkedIn": "PhantomBuster"
        }
        
        mcc = MockMultiChannelCadence()
        
        # Call the method manually using the class function
        MultiChannelCadence.before_insert(mcc)
        
        mock_resolve.assert_called_once_with("MCC-001")
        self.assertEqual(len(mcc.provider), 2)

        channels = {row.channel: row.cadence_provider for row in mcc.provider}
        self.assertEqual(channels["Email"], "Apollo")
        self.assertEqual(channels["LinkedIn"], "PhantomBuster")

    @patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.frappe.get_all")
    @patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.enqueue")
    @patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.frappe.get_doc")
    def test_mcc_status_change_broadcast(self, mock_get_doc, mock_enqueue, mock_get_all):
        from frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence import MultiChannelCadence
        
        mcc = MockMultiChannelCadence()
        mcc.status = "In Progress"
        
        # Mock parent cadence
        mock_get_doc.return_value = MagicMock() 
        mock_get_all.return_value = []
        
        # Add mock child table
        mcc.append("provider", {"channel": "Email", "cadence_provider": "Apollo"})
        mcc.append("provider", {"channel": "LinkedIn", "cadence_provider": "PhantomBuster"})
        
        # Trigger on_update
        MultiChannelCadence.on_update(mcc)
        
        # Verify enqueue was called for each unique provider
        enqueued_providers = []
        for call in mock_enqueue.call_args_list:
            kwargs = call[1]
            if kwargs.get("event_method") == "on_mcc_status_changed":
                enqueued_providers.append(kwargs.get("provider_name"))
        
        self.assertIn("Apollo", enqueued_providers)
        self.assertIn("PhantomBuster", enqueued_providers)
        self.assertEqual(len(enqueued_providers), 2)
import frappe
from frappe.tests import UnitTestCase
from unittest.mock import patch, MagicMock
from frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence import MultiChannelCadence

class TestMultiChannelCadenceLifecycle(UnitTestCase):

    @patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.frappe.get_all")
    @patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.enqueue")
    @patch("frappe.get_doc")
    def test_mcc_status_update_triggers_broadcast(self, mock_get_doc, mock_enqueue, mock_get_all):
        mock_get_all.return_value = []
        mock_cadence = MagicMock()
        mock_cadence.provider = "Dummy"
        mock_get_doc.return_value = mock_cadence
        
        mcc = MultiChannelCadence({"doctype": "Multi Channel Cadence"})
        mcc.cadence_name = "Cadence-1"
        mcc.status = "Scheduled"
        mcc.provider = [MagicMock(cadence_provider="Dummy")]
        mcc.get_doc_before_save = MagicMock(return_value=MagicMock(status="Draft", provider=[]))
        mcc.has_value_changed = MagicMock(return_value=True)
        
        mcc.on_update()
        
        mock_enqueue.assert_any_call(
            "frappe_cadence.cadence.doctype.cadence_provider.cadence_provider.broadcast_event",
            queue="low",
            provider_name="Dummy",
            event_method="on_mcc_status_changed",
            mcc_doc=mcc,
            old_status="Draft",
            new_status="Scheduled"
        )

    @patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.frappe.get_all")
    @patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.enqueue")
    @patch("frappe.get_doc")
    def test_provider_agnostic_mcc_lifecycle(self, mock_get_doc, mock_enqueue, mock_get_all):
        mock_get_all.return_value = []
        mock_cadence = MagicMock()
        mock_cadence.provider = None
        sch = MagicMock()
        sch.name = "Sch-1"
        mock_cadence.cadence_schedules = [sch]
        mock_get_doc.return_value = mock_cadence
        
        mcc = MultiChannelCadence({"doctype": "Multi Channel Cadence"})
        mcc.cadence_name = "Cadence-1"
        mcc.status = "Scheduled"
        mcc.name = "MCC-1"
        mcc.provider = []
        mcc.get_doc_before_save = MagicMock(return_value=MagicMock(status="Draft"))
        mcc.has_value_changed = MagicMock(return_value=True)
        
        mcc.on_update()
        
        # enqueue should NOT be called for broadcast_event
        for call in mock_enqueue.call_args_list:
            self.assertNotEqual(call[0][0], "frappe_cadence.cadence.doctype.cadence_provider.cadence_provider.broadcast_event")

        # It should enqueue the native process_schedule
        mock_enqueue.assert_any_call(
            "frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.process_schedule",
            queue="medium",
            cadence_name="MCC-1",
            schedule_name="Sch-1",
            previous_schedule_name=None
        )

    @patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.frappe.get_all")
    @patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.frappe.get_doc")
    def test_mcc_on_update_cascade_updates_communication(self, mock_get_doc, mock_get_all):
        # Setup mock doc
        mcc = MultiChannelCadence({"doctype": "Multi Channel Cadence", "name": "MCC-Cascade"})
        mcc.cadence_name = "Cadence-Cascade"
        
        # New provider
        mock_new_provider = MagicMock(channel="Email", cadence_provider="Apollo")
        mcc.provider = [mock_new_provider]
        
        # Old provider (none)
        mock_old_mcc = MagicMock(status="Scheduled", provider=[])
        mcc.get_doc_before_save = MagicMock(return_value=mock_old_mcc)
        
        mcc.has_value_changed = MagicMock(return_value=False)
        
        # Mock communication
        mock_comm_info = MagicMock(name="COMM-1")
        mock_get_all.return_value = [mock_comm_info]
        
        mock_comm = MagicMock()
        mock_get_doc.return_value = mock_comm
        
        mcc.on_update()
        
        # Verify get_all called for orphaned communications
        mock_get_all.assert_called_with("Communication", filters={
            "reference_doctype": "Multi Channel Cadence",
            "reference_name": "MCC-Cascade",
            "communication_medium": "Email",
            "reference_cadence_provider": ["is", "not set"]
        })
        
        # Verify communication updated and saved
        self.assertEqual(mock_comm.reference_cadence_provider, "Apollo")
        mock_comm.save.assert_called_with(ignore_permissions=True)
import unittest
from unittest.mock import patch, MagicMock
import frappe
from frappe.tests import UnitTestCase

class TestMultiChannelCadence(UnitTestCase):

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

    @patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.frappe.get_doc")
    @patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.frappe.get_all")
    @patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.emit_event")
    def test_process_cadence_step_communication_generation(self, mock_emit_event, mock_get_all, mock_get_doc):
        from frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence import process_schedule
        
        # Setup mocks
        # 1. First get_all checks for idempotency, return empty list to proceed
        mock_get_all.return_value = []
        
        # 2. Setup mock documents
        mock_schedule = MagicMock()
        mock_schedule.reference_doctype = "Email Template"
        mock_schedule.reference_name = "Template-001"
        
        mock_mcc = MagicMock()
        mock_mcc.status = "Scheduled"
        row = MagicMock()
        row.channel = "Email"
        row.cadence_provider = "Apollo"
        mock_mcc.get.return_value = [row]
        
        mock_template = MagicMock()
        mock_template.status = "Enabled"
        mock_template.subject = "Test Subject"
        mock_template.message = "Test Message"
        mock_template.get.side_effect = lambda k, default=None: getattr(mock_template, k, default)
        
        mock_comm = MagicMock()
        
        original_get_doc = frappe.get_doc
        def get_doc_side_effect(*args, **kwargs):
            if len(args) == 2 and args[0] == "Cadence Multi Channel Schedule":
                return mock_schedule
            elif len(args) == 2 and args[0] == "Multi Channel Cadence":
                return mock_mcc
            elif len(args) == 2 and args[0] == "Email Template":
                return mock_template
            elif len(args) == 1 and isinstance(args[0], dict) and args[0].get("doctype") == "Communication":
                # Intercept Communication creation to verify kwargs
                for k, v in args[0].items():
                    setattr(mock_comm, k, v)
                return mock_comm
            return original_get_doc(*args, **kwargs)
            
        mock_get_doc.side_effect = get_doc_side_effect
        
        # Act
        process_schedule("MCC-001", "SCHED-001")
        
        # Assert
        self.assertEqual(mock_comm.doctype, "Communication")
        self.assertEqual(mock_comm.reference_cadence_provider, "Apollo")
        self.assertEqual(mock_comm.communication_medium, "Email")
        mock_comm.insert.assert_called_once_with(ignore_permissions=True)
        mock_emit_event.assert_called_once_with("cadence_step_completed", {"cadence_name": "MCC-001", "schedule_name": "SCHED-001"})

    @patch("frappe_cadence.cadence.doctype.history.history.get_history")
    @patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.requests.post")
    @patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.wait_for_event")
    @patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.frappe.get_all")
    @patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.get_url")
    @patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.add_months")
    @patch("frappe_cadence.cadence.doctype.user_bio.user_bio.get_user_bio")
    def test_process_cadence_step_sift_integration(self, mock_get_user_bio, mock_add_months, mock_get_url, mock_get_all, mock_wait_for_event, mock_post, mock_get_history):
        mock_get_user_bio.return_value = "<p>I am a <strong>bold</strong> user.</p>"
        mock_get_url.return_value = "http://test.com/webhook"
        mock_add_months.return_value = "2024-01-01"
        from frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence import process_schedule
        import json
        
        # Setup Sift settings
        mock_sift_settings = MagicMock()
        mock_sift_settings.sift_base_url = "https://api.sift.com"
        mock_sift_settings.get_password.return_value = "sift_secret_key"

        # Setup mock documents
        mock_schedule = MagicMock()
        mock_schedule.reference_doctype = "Email Template"
        mock_schedule.reference_name = "Template-002"
        
        mock_mcc = MagicMock()
        mock_mcc.status = "Scheduled"
        mock_mcc.cadence_for = "CRM Lead"
        mock_mcc.recipient = "LEAD-001"
        mock_mcc.owner = "user@test.com"
        mock_mcc.sift_id = "agent-mcc"
        row = MagicMock()
        row.channel = "Email"
        row.cadence_provider = "Apollo"
        mock_mcc.get.return_value = [row]
        
        mock_template = MagicMock()
        mock_template.status = "Prompt"
        
        mock_lead = MagicMock()
        mock_lead.name = "LEAD-001"
        mock_lead.organization = "ORG-001"
        
        mock_comm = MagicMock()
        mock_comm.name = "COMM-001"
        
        mock_get_history.return_value = [
            {"role": "user", "content": [{"type": "text", "text": "Test History"}, {"type": "image_url", "image_url": {"url": "https://s3.example.com/test.png?sig=123"}}]}
        ]
        
        # Mock get_all
        def get_all_side_effect(doctype, *args, **kwargs):
            if doctype == "Communication":
                return []
            return []
            
        mock_get_all.side_effect = get_all_side_effect
        
        original_get_doc = frappe.get_doc
        def get_doc_side_effect(*args, **kwargs):
            if len(args) == 2 and args[0] == "Cadence Multi Channel Schedule":
                return mock_schedule
            elif len(args) == 2 and args[0] == "Multi Channel Cadence":
                return mock_mcc
            elif len(args) == 2 and args[0] == "Email Template":
                return mock_template
            elif len(args) == 2 and args[0] == "CRM Lead":
                return mock_lead
            elif len(args) == 1 and isinstance(args[0], dict) and args[0].get("doctype") == "Communication":
                return mock_comm
            return original_get_doc(*args, **kwargs)
            
        original_get_single = frappe.get_single
        def get_single_side_effect(*args, **kwargs):
            if args[0] == "Sift Settings":
                return mock_sift_settings
            return original_get_single(*args, **kwargs)
            
        original_get_value = frappe.db.get_value
        def get_value_side_effect(*args, **kwargs):
            doctype = kwargs.get("doctype") or (args[0] if len(args) > 0 else None)
            filters = kwargs.get("filters") or (args[1] if len(args) > 1 else None)
            if doctype == "User" and filters == "user@test.com":
                return {"full_name": "Test User", "bio": "<p>I am a <strong>bold</strong> user.</p>"}
            return original_get_value(*args, **kwargs)
            
        with patch.object(frappe, "get_doc", side_effect=get_doc_side_effect):
            with patch.object(frappe, "get_single", side_effect=get_single_side_effect):
                with patch.object(frappe.db, "get_value", side_effect=get_value_side_effect):
                    with patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.frappe.cache") as mock_cache:
                        mock_cache.return_value.get_value.return_value = None
                        process_schedule("MCC-001", "SCHED-001")
                    
                    # Assert
                    mock_post.assert_called_once()
                    called_url = mock_post.call_args[0][0]
                    self.assertEqual(called_url, "https://api.sift.com/responses")
                    
                    headers = mock_post.call_args[1]["headers"]
                    self.assertEqual(headers["Authorization"], "Bearer sift_secret_key")
                    
                    data = json.loads(mock_post.call_args[1]["data"])
                    self.assertTrue(data.get("background"))
                    self.assertIn("webhook", data)
                    self.assertEqual(data["webhook"]["url"], "http://test.com/webhook")
                    self.assertEqual(data["webhook"]["events"], ["completed", "failed"])
                    self.assertEqual(data["model"], "agent-mcc")
                    
                    # Verify input payload structure
                    input_data = data["input"]
                    self.assertEqual(len(input_data), 2) # System, History
                    
                    self.assertEqual(input_data[0]["role"], "system")
                    self.assertIn("Test User", input_data[0]["content"])
                    
                    self.assertEqual(input_data[1]["role"], "user")
                    self.assertEqual(len(input_data[1]["content"]), 2) # text + image
                    self.assertEqual(input_data[1]["content"][0]["type"], "text")
                    self.assertEqual(input_data[1]["content"][0]["text"], "Test History")
                    self.assertEqual(input_data[1]["content"][1]["type"], "image_url")
                    self.assertEqual(input_data[1]["content"][1]["image_url"]["url"], "https://s3.example.com/test.png?sig=123")
                    
                    mock_wait_for_event.assert_called_once_with(
                        "callback",
                        condition="argument.get('communication_id') == 'COMM-001'"
                    )

    @patch("frappe_cadence.cadence.doctype.history.history.get_history")
    @patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.requests.post")
    @patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.wait_for_event")
    @patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.frappe.get_all")
    @patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.get_url")
    @patch("frappe_cadence.cadence.doctype.user_bio.user_bio.get_user_bio")
    def test_process_cadence_step_sift_payload_markdown(self, mock_get_user_bio, mock_get_url, mock_get_all, mock_wait_for_event, mock_post, mock_get_history):
        mock_get_url.return_value = "http://test.com/webhook"
        from frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence import process_schedule
        import json
        
        # Setup Sift settings
        mock_sift_settings = MagicMock()
        mock_sift_settings.sift_base_url = "https://api.sift.com"
        mock_sift_settings.get_password.return_value = "sift_secret_key"

        # Setup mock documents
        mock_schedule = MagicMock()
        mock_schedule.reference_doctype = "Email Template"
        mock_schedule.reference_name = "Template-003"
        
        mock_mcc = MagicMock()
        mock_mcc.status = "Scheduled"
        mock_mcc.cadence_for = "CRM Lead"
        mock_mcc.recipient = "LEAD-002"
        mock_mcc.owner = "user@test.com"
        mock_mcc.sift_id = "agent-mcc-2"
        row = MagicMock()
        row.channel = "Email"
        row.cadence_provider = "Apollo"
        mock_mcc.get.return_value = [row]
        
        mock_template = MagicMock()
        mock_template.status = "Prompt"
        
        mock_lead = MagicMock()
        mock_lead.name = "LEAD-002"
        mock_lead.organization = None
        
        mock_comm = MagicMock()
        mock_comm.name = "COMM-002"
        
        mock_get_history.return_value = []
        
        # Mock get_all to return no drafts and no history
        def get_all_side_effect(doctype, *args, **kwargs):
            return []
            
        mock_get_all.side_effect = get_all_side_effect
        
        original_get_doc = frappe.get_doc
        def get_doc_side_effect(*args, **kwargs):
            if len(args) == 2 and args[0] == "Cadence Multi Channel Schedule":
                return mock_schedule
            elif len(args) == 2 and args[0] == "Multi Channel Cadence":
                return mock_mcc
            elif len(args) == 2 and args[0] == "Email Template":
                return mock_template
            elif len(args) == 2 and args[0] == "CRM Lead":
                return mock_lead
            elif len(args) == 1 and isinstance(args[0], dict) and args[0].get("doctype") == "Communication":
                return mock_comm
            return original_get_doc(*args, **kwargs)
            
        original_get_single = frappe.get_single
        def get_single_side_effect(*args, **kwargs):
            if args[0] == "Sift Settings":
                return mock_sift_settings
            return original_get_single(*args, **kwargs)
            
        mock_get_user_bio.return_value = "<p>I am a <strong>bold</strong> user.</p>"
        
        # Mock frappe.db.get_value to return HTML bio
        original_get_value = frappe.db.get_value
        def get_value_side_effect(*args, **kwargs):
            doctype = kwargs.get("doctype") or (args[0] if len(args) > 0 else None)
            filters = kwargs.get("filters") or (args[1] if len(args) > 1 else None)
            if doctype == "User" and filters == "user@test.com":
                return {"full_name": "Test User"}
            return original_get_value(*args, **kwargs)
            
        with patch.object(frappe, "get_doc", side_effect=get_doc_side_effect):
            with patch.object(frappe, "get_single", side_effect=get_single_side_effect):
                with patch.object(frappe.db, "get_value", side_effect=get_value_side_effect):
                    with patch("frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.frappe.cache") as mock_cache:
                        mock_cache.return_value.get_value.return_value = None
                        process_schedule("MCC-002", "SCHED-002")
                        
                        # Assert
                        mock_post.assert_called_once()
                        data = json.loads(mock_post.call_args[1]["data"])
                        
                        input_data = data["input"]
                        system_content = input_data[0]["content"]
                        
                        self.assertIn("Sender Name: Test User", system_content)
                        self.assertIn("I am a **bold** user.", system_content)
