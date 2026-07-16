import frappe
import vcr
import vcr.patch
import os

# Fix aiohttp vcrpy compatibility bug
def empty_generator(*args, **kwargs):
    yield from []
vcr.patch.CassettePatcherBuilder._aiohttp = empty_generator

from frappe.tests import IntegrationTestCase
from frappe_cadence.integrations.sift import optimize, predict

# Define the cassettes directory relative to this file
CASSETTES_DIR = os.path.join(os.path.dirname(__file__), "cassettes")

my_vcr = vcr.VCR(
    cassette_library_dir=CASSETTES_DIR,
    record_mode="once",
    match_on=["method", "scheme", "host", "port", "path"],
    filter_headers=["authorization"]
)

class TestSiftExternalIntegration(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        frappe.db.rollback()
        super().tearDownClass()

    @my_vcr.use_cassette("test_optimize_external.yaml")
    def test_optimize_external(self):
        settings = frappe.get_single("Sift Settings")
        settings.sift_base_url = frappe.conf.get("sift_base_url") or "https://windmill.aurumor.com/api/w/aurumor/jobs/run/p/f/sift"
        settings.sift_api_key = frappe.conf.get("sift_api_key") or "test-key"
        settings.save(ignore_permissions=True)

        # 2. Setup Models
        provider = frappe.get_doc({
            "doctype": "Model Provider",
            "model_provider_name": "TestProvider"
        })
        provider.insert(ignore_permissions=True, ignore_if_duplicate=True)

        model = frappe.get_doc({
            "doctype": "Model",
            "model_name": "test-model",
            "provider": provider.name
        })
        model.insert(ignore_permissions=True, ignore_if_duplicate=True)

        # 3. Setup Template
        template = frappe.get_doc({
            "doctype": "Email Template",
            "name": "External Test Template",
            "title": "External Test Template",
            "subject": "External Test",
            "model": model.name,
            "status": "Enabled"
        })
        template.insert(ignore_permissions=True)

        # 4. Setup Annotation
        lead = frappe.get_doc({
            "doctype": "CRM Lead",
            "lead_name": "Ext Lead",
            "first_name": "External",
            "email_id": "ext@example.com"
        })
        lead.insert(ignore_permissions=True)

        annotation = frappe.get_doc({
            "doctype": "Email Template Annotation",
            "parent": template.name,
            "parentfield": "annotations",
            "parenttype": "Email Template",
            "reference_doctype": "CRM Lead",
            "reference_name": lead.name,
            "sender": "Administrator",
            "subject": "External Subject",
            "salutation": "External Salutation",
            "body": "External Body",
            "cta": "External CTA",
            "sign_off": "External Sign Off"
        })
        annotation.insert(ignore_permissions=True)

        

        # Execute optimize which will make a real HTTP request unless cached by VCR
        optimize(template.doctype, template.name)
        template.reload()
        self.assertEqual(template.status, "Optimizing")

    @my_vcr.use_cassette("test_predict_external.yaml")
    def test_predict_external(self):
        settings = frappe.get_single("Sift Settings")
        settings.sift_base_url = frappe.conf.get("sift_base_url") or "https://windmill.aurumor.com/api/w/aurumor/jobs/run/p/f/sift"
        settings.sift_api_key = frappe.conf.get("sift_api_key") or "test-key"
        settings.save(ignore_permissions=True)

        # 2. Setup Models & Template
        template = frappe.get_doc({
            "doctype": "Email Template",
            "name": "External Test Predict Template",
            "title": "External Test Predict Template",
            "subject": "External Test",
            "status": "Enabled",
            "sift_id": "sift-agent-external-123"
        })
        template.insert(ignore_permissions=True)

        # 3. Setup Annotation with missing outputs (Pending)
        lead = frappe.get_doc({
            "doctype": "CRM Lead",
            "lead_name": "Ext Lead Predict",
            "first_name": "External",
            "email_id": "ext_pred@example.com"
        })
        lead.insert(ignore_permissions=True)

        annotation = frappe.get_doc({
            "doctype": "Email Template Annotation",
            "parent": template.name,
            "parentfield": "annotations",
            "parenttype": "Email Template",
            "reference_doctype": "CRM Lead",
            "reference_name": lead.name,
            "sender": "Administrator"
        })
        annotation.insert(ignore_permissions=True)

        

        # Execute predict
        predict(template.doctype, template.name)
        template.reload()
        self.assertEqual(template.status, "Predicting")
