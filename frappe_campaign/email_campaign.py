import frappe
from frappe import _
import json
from markdownify import markdownify as md

class LazyNotesList:
	def __init__(self, doctype, name):
		self.doctype = doctype
		self.name = name
		self._notes = None

	def _load(self):
		if self._notes is None:
			self._notes = frappe.get_all(
				"FCRM Note",
				filters={"reference_doctype": self.doctype, "reference_docname": self.name},
				fields=["*"]
			)
		return self._notes

	def __iter__(self):
		return iter(self._load() or [])

	def __len__(self):
		return len(self._load() or [])

	def __bool__(self):
		return bool(self._load())


class LazyDocumentLink(str):
	def __new__(cls, name, doctype):
		obj = super().__new__(cls, name or "")
		obj.doctype = doctype
		obj.docname = name
		obj._doc = None
		obj._as_dict = None
		return obj

	def _load(self):
		if self._as_dict is None:
			if not self.docname:
				self._as_dict = {}
				return self._as_dict
			try:
				self._doc = frappe.get_doc(self.doctype, self.docname)
				self._as_dict = self._doc.as_dict()
			except Exception:
				self._as_dict = {}
		return self._as_dict

	def __getattr__(self, key):
		if key in ("doctype", "docname", "_doc", "_as_dict", "_load"):
			return super().__getattribute__(key)

		data = self._load()
		if key in data:
			val = data[key]

			# Lazy relationships
			if key == "organization" and val and type(val) is str:
				lazy_val = LazyDocumentLink(val, "CRM Organization")
				data[key] = lazy_val
				return lazy_val

			return val

		if key == "fcrm_notes":
			if "fcrm_notes" not in data:
				data["fcrm_notes"] = LazyNotesList(self.doctype, self.docname)
			return data["fcrm_notes"]

		return None


class LazyProp:
	def __init__(self, doc_link, key):
		self.doc_link = doc_link
		self.key = key

	def _val(self):
		return getattr(self.doc_link, self.key, None)

	def __str__(self):
		val = self._val()
		return str(val) if val is not None else ""

	def __bool__(self):
		return bool(self._val())

	def __iter__(self):
		v = self._val()
		if not v:
			return iter([])
		return iter(v)

	def __getattr__(self, key):
		val = self._val()
		if val is None:
			return None
		return getattr(val, key)


@frappe.whitelist()
def get(name=None, filters=None):
	"""
	Highly efficient endpoint for n8n to fetch all context in a single network request.
	Returns the exact Email Campaign document structure, but with the 'recipient' 
	field enriched to contain the full CRM Lead, Organization, and FCRM Notes.
	Accepts either 'name' directly, or standard Frappe 'filters'.
	"""
	if filters:
		if isinstance(filters, str):
			filters = json.loads(filters)
			
		matched_campaigns = frappe.get_all("Email Campaign", filters=filters, pluck="name", limit=1)
		if not matched_campaigns:
			frappe.throw(_("Email Campaign not found matching filters"), frappe.DoesNotExistError)
		name = matched_campaigns[0]
			
	if not name:
		frappe.throw(_("Please provide name or filters"), frappe.ValidationError)
		
	campaign = frappe.get_doc("Email Campaign", name)
	payload = campaign.as_dict()
	
	if campaign.campaign_name:
		payload["campaign_name"] = frappe.get_doc("Campaign", campaign.campaign_name).as_dict()
		
		# Dynamically weave Apollo Sequence Config
		sequence = frappe.get_all(
			"Sequence",
			filters={"campaign": campaign.campaign_name, "sender": campaign.sender},
			fields=["name", "emailer_campaign_id", "email_account_id"],
			limit=1
		)
		if sequence:
			payload["emailer_campaign_id"] = sequence[0].emailer_campaign_id
			payload["email_account_id"] = sequence[0].email_account_id
			
			seq_steps = frappe.get_all(
				"Sequence Step",
				filters={"parent": sequence[0].name},
				fields=["idx", "subject_custom_field_id", "response_custom_field_id"]
			)
			step_map = {str(step.idx): step for step in seq_steps}
		else:
			step_map = {}

	# Prepare Jinja Context (kept separate from payload so n8n only gets rendered prompts)
	context = payload.copy()
	
	if campaign.email_campaign_for == "CRM Lead":
		lead_link = LazyDocumentLink(campaign.recipient, "CRM Lead")
		
		# Lazily populate the context with CRM Lead fields
		meta = frappe.get_meta("CRM Lead")
		for f in meta.fields:
			context[f.fieldname] = LazyProp(lead_link, f.fieldname)
			
		standard_fields = ["name", "owner", "creation", "modified", "modified_by"]
		for f in standard_fields:
			context[f] = LazyProp(lead_link, f)
			
		context["fcrm_notes"] = LazyProp(lead_link, "fcrm_notes")
		context["recipient"] = lead_link # Keep it available via {{ recipient.first_name }} too

	# Process Email Schedules
	for schedule in payload.get("campaign_email_schedules", []):
		if schedule.get("email_template"):
			template_doc = frappe.get_doc("Email Template", schedule["email_template"])
			template_dict = template_doc.as_dict()

			# Render prompts if they exist
			if template_dict.get("user_prompt"):
				rendered_html = frappe.render_template(template_dict["user_prompt"], context)
				template_dict["user_prompt"] = md(rendered_html).strip()
			
			if template_dict.get("system_prompt"):
				rendered_html = frappe.render_template(template_dict["system_prompt"], context)
				template_dict["system_prompt"] = md(rendered_html).strip()
			
			# Replace the string ID with the fully enriched template object
			schedule["email_template"] = template_dict

		# Dynamically weave Step IDs
		s_idx = str(schedule.get("idx"))
		if s_idx in step_map:
			schedule["subject_apollo_id"] = step_map[s_idx].subject_custom_field_id
			schedule["response_apollo_id"] = step_map[s_idx].response_custom_field_id

	return payload

@frappe.whitelist()
def update(name, campaign_email_schedules):
	"""
	API for n8n to update email schedules.
	Only accepts updates if status is empty (needs generation).
	"""
	campaign = frappe.get_doc("Email Campaign", name)
	
	if campaign.status not in ["", None, "Draft"]:
		# Ignore retry requests if already generated or failed to prevent Convoy from getting stuck in a retry loop
		return {"status": "ignored", "reason": "Campaign status is already {0}".format(campaign.status)}
	
	if isinstance(campaign_email_schedules, str):
		campaign_email_schedules = json.loads(campaign_email_schedules)
		
	# if a single dictionary is passed instead of a list, wrap it in a list
	if isinstance(campaign_email_schedules, dict):
		campaign_email_schedules = [campaign_email_schedules]
		
	for s_data in campaign_email_schedules:
		for s in campaign.campaign_email_schedules:
			# match by name or by idx
			if s.name == s_data.get("name") or (s_data.get("idx") and s.idx == int(s_data.get("idx"))):
				# Dynamically update any field provided in the payload
				for field_name, value in s_data.items():
					if field_name not in ["name", "idx"]:
						s.set(field_name, value)
				break
	
	campaign.flags.ignore_validate = True
	campaign.save(ignore_permissions=True)
	return {"status": "success"}
