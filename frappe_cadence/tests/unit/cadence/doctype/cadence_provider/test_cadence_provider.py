import frappe
from frappe.tests import UnitTestCase
from frappe_cadence.cadence.doctype.cadence_provider.cadence_provider import BaseCadenceProvider, get_provider_instance, broadcast_event, on_cadence_update
from unittest.mock import patch, MagicMock

class DummyCadenceProvider(BaseCadenceProvider):
    def on_mcc_status_changed(self, mcc_doc, old_status, new_status):
        pass

class TestCadenceProviderInterface(UnitTestCase):

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

    @patch("frappe_cadence.cadence.doctype.cadence_provider.cadence_provider.frappe.get_hooks")
    def test_get_provider_instance_success(self, mock_get_hooks):
        mock_get_hooks.return_value = {
            "Dummy": "frappe_cadence.tests.unit.cadence.doctype.cadence_provider.test_cadence_provider.DummyCadenceProvider"
        }
        
        provider = get_provider_instance("Dummy")
        self.assertIsInstance(provider, DummyCadenceProvider)

    @patch("frappe_cadence.cadence.doctype.cadence_provider.cadence_provider.frappe.get_hooks")
    def test_get_provider_instance_missing(self, mock_get_hooks):
        mock_get_hooks.return_value = {}
        
        with self.assertRaises(ValueError):
            get_provider_instance("NonExistent")

    @patch("frappe_cadence.cadence.doctype.cadence_provider.cadence_provider.get_provider_instance")
    def test_broadcast_event_dispatch(self, mock_get_provider_instance):
        mock_provider = MagicMock(spec=DummyCadenceProvider)
        mock_get_provider_instance.return_value = mock_provider
        
        mcc_doc = MagicMock()
        
        broadcast_event("Dummy", "on_mcc_status_changed", mcc_doc, "Draft", "Scheduled")
        
        mock_provider.on_mcc_status_changed.assert_called_once_with(mcc_doc, "Draft", "Scheduled")

    @patch("frappe_cadence.cadence.doctype.cadence_provider.cadence_provider.frappe.get_all")
    @patch("frappe_cadence.cadence.doctype.cadence_provider.cadence_provider.broadcast_event")
    def test_on_cadence_update_broadcasting(self, mock_broadcast_event, mock_get_all):
        mock_get_all.return_value = ["Apollo", "TestProvider"]
        
        mock_doc = MagicMock()
        on_cadence_update(mock_doc)
        
        mock_get_all.assert_called_once_with(
            "Cadence Provider",
            filters={"enabled": 1},
            pluck="name"
        )
        self.assertEqual(mock_broadcast_event.call_count, 2)

import unittest
from unittest.mock import patch
import hashlib
from frappe_cadence.cadence.doctype.cadence_provider.cadence_provider import resolve_providers_for_mcc

class TestProviderRouter(UnitTestCase):
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

    @patch("frappe_cadence.cadence.doctype.cadence_provider.cadence_provider.frappe.get_all")
    def test_resolve_providers_for_mcc_deterministic_routing(self, mock_get_all):
        def mock_get_all_side_effect(doctype, *args, **kwargs):
            if doctype == "Cadence Provider":
                return [frappe._dict({"name": "Apollo"}), frappe._dict({"name": "SendGrid"}), frappe._dict({"name": "Mailgun"})]
            elif doctype == "Cadence Provider Channel":
                parent = kwargs.get("filters", {}).get("parent")
                if parent == "Apollo":
                    return [frappe._dict(channel="Email", priority=1)]
                elif parent == "SendGrid":
                    return [frappe._dict(channel="Email", priority=1)]
                elif parent == "Mailgun":
                    return [frappe._dict(channel="Email", priority=1)]
            return []
            
        mock_get_all.side_effect = mock_get_all_side_effect
        
        results = {"Apollo": 0, "SendGrid": 0, "Mailgun": 0}
        
        for i in range(100):
            mcc_name = f"dummy_mcc_{i}"
            res = resolve_providers_for_mcc(mcc_name)
            self.assertIn("Email", res)
            results[res["Email"]] += 1
            
            # test stability
            res_again = resolve_providers_for_mcc(mcc_name)
            self.assertEqual(res["Email"], res_again["Email"])
            
        # Ensure relatively balanced distribution
        for count in results.values():
            self.assertGreater(count, 15)
            self.assertLess(count, 55)

    @patch("frappe_cadence.cadence.doctype.cadence_provider.cadence_provider.frappe.get_all")
    def test_resolve_providers_for_mcc_weighted_priorities(self, mock_get_all):
        def mock_get_all_side_effect(doctype, *args, **kwargs):
            if doctype == "Cadence Provider":
                return [frappe._dict({"name": "Apollo"}), frappe._dict({"name": "SendGrid"})]
            elif doctype == "Cadence Provider Channel":
                parent = kwargs.get("filters", {}).get("parent")
                if parent == "Apollo":
                    return [frappe._dict(channel="Email", priority=80)]
                elif parent == "SendGrid":
                    return [frappe._dict(channel="Email", priority=20)]
            return []
            
        mock_get_all.side_effect = mock_get_all_side_effect
        
        results = {"Apollo": 0, "SendGrid": 0}
        
        for i in range(1000):
            mcc_name = f"dummy_mcc_{i}"
            res = resolve_providers_for_mcc(mcc_name)
            results[res["Email"]] += 1
            
        # Check distribution is roughly 80/20
        self.assertGreater(results["Apollo"], 750)
        self.assertLess(results["Apollo"], 850)
        self.assertGreater(results["SendGrid"], 150)
        self.assertLess(results["SendGrid"], 250)

    @patch("frappe_cadence.cadence.doctype.cadence_provider.cadence_provider.frappe.get_all")
    def test_resolve_providers_for_mcc_missing_channel(self, mock_get_all):
        def mock_get_all_side_effect(doctype, *args, **kwargs):
            if doctype == "Cadence Provider":
                return [frappe._dict({"name": "Apollo"})]
            elif doctype == "Cadence Provider Channel":
                parent = kwargs.get("filters", {}).get("parent")
                if parent == "Apollo":
                    return [frappe._dict(channel="Email", priority=1)]
            return []
            
        mock_get_all.side_effect = mock_get_all_side_effect
        
        res = resolve_providers_for_mcc("mcc_1")
        self.assertIn("Email", res)
        self.assertNotIn("SMS", res)
