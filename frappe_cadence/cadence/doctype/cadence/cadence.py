# Copyright (c) 2021, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class Cadence(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.automation.doctype.assignment_rule_user.assignment_rule_user import AssignmentRuleUser
		from frappe.types import DF
		from frappe_cadence.cadence.doctype.cadence_provider_channel.cadence_provider_channel import CadenceProviderChannel
		from frappe_cadence.cadence.doctype.cadence_multi_channel_schedule.cadence_multi_channel_schedule import CadenceMultiChannelSchedule

		assign_condition: DF.Code | None
		assign_condition_json: DF.Code | None
		cadence_code: DF.Data
		cadence_name: DF.Data
		cadence_schedules: DF.Table[CadenceMultiChannelSchedule]
		provider: DF.Table[CadenceProviderChannel]
		description: DF.Text | None
		last_user: DF.Link | None
		naming_series: DF.Literal["CAD-.YYYY.-"]
		reference_playbook: DF.Link | None
		rule: DF.Literal["Round Robin", "Load Balancing"]
		users: DF.TableMultiSelect[AssignmentRuleUser]
	# end: auto-generated types

	def autoname(self):
		if not self.cadence_code:
			from frappe.model.naming import set_name_by_naming_series
			set_name_by_naming_series(self)
			self.cadence_code = self.name
		self.name = self.cadence_code

	def after_insert(self):
		self.ensure_playbook()
		if frappe.db.exists("UTM Campaign", self.name):
			mc = frappe.get_doc("UTM Campaign", self.name)
		else:
			mc = frappe.new_doc("UTM Campaign")
			mc.name = self.name
		mc.cadence_description = self.description
		mc.crm_cadence = self.name
		mc.save(ignore_permissions=True)

	def before_save(self):
		import ast
		import json

		if not self.assign_condition:
			self.assign_condition_json = ""
			return

		try:
			tree = ast.parse(self.assign_condition, mode='eval')
			filters = self._ast_to_filters(tree.body)
			self.assign_condition_json = json.dumps(filters)
		except Exception as e:
			frappe.throw(f"Invalid condition syntax: {str(e)}", frappe.ValidationError)

	def _ast_to_filters(self, node):
		import ast

		operators = {
			ast.Eq: "=",
			ast.NotEq: "!=",
			ast.Gt: ">",
			ast.Lt: "<",
			ast.GtE: ">=",
			ast.LtE: "<=",
			ast.In: "in",
			ast.NotIn: "not in",
			ast.Is: "is",
		}

		if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.And):
			filters = []
			for val in node.values:
				filters.extend(self._ast_to_filters(val))
			return filters

		elif isinstance(node, ast.Compare):
			if len(node.ops) != 1 or len(node.comparators) != 1:
				raise ValueError("Only simple comparisons are supported")

			op = type(node.ops[0])
			if op not in operators:
				raise ValueError(f"Unsupported operator: {op.__name__}")

			left = node.left
			if not (isinstance(left, ast.Attribute) and isinstance(left.value, ast.Name) and left.value.id == "doc"):
				raise ValueError("Left side of comparison must be a doc attribute (e.g., doc.status)")

			fieldname = left.attr

			right = node.comparators[0]
			if isinstance(right, ast.Constant):
				value = right.value
			elif isinstance(right, (ast.List, ast.Tuple)):
				value = [el.value for el in right.elts if isinstance(el, ast.Constant)]
			else:
				raise ValueError("Right side of comparison must be a constant or a list of constants")

			if op == ast.Eq and isinstance(value, list) and len(value) == 2 and isinstance(value[0], str) and value[0].lower() in ("like", "not like"):
				return [[fieldname, value[0].lower(), value[1]]]

			return [[fieldname, operators[op], value]]

		else:
			raise ValueError("Unsupported expression structure")

	def on_change(self):
		if frappe.db.exists("UTM Campaign", self.name):
			mc = frappe.get_doc("UTM Campaign", self.name)
		else:
			mc = frappe.new_doc("UTM Campaign")
			mc.name = self.name
		mc.cadence_description = self.description
		mc.crm_cadence = self.name
		mc.save(ignore_permissions=True)

	def on_update(self):
		from frappe_controller.utils.background_jobs import enqueue

		self.ensure_playbook()
		enqueue(
			"frappe_cadence.cadence.doctype.cadence_provider.cadence_provider.on_cadence_update",
			queue="low",
			doc=self
		)
		enqueue(
			"frappe_cadence.cadence.doctype.cadence.cadence.evaluate_cadence_for_leads",
			queue="low",
			cadence_name=self.name
		)

	def ensure_playbook(self):
		if not self.get("reference_playbook"):
			try:
				if frappe.db.exists("Playbook", self.name):
					self.db_set("reference_playbook", self.name)
					self.reference_playbook = self.name
				else:
					playbook = frappe.get_doc({
						"doctype": "Playbook",
						"playbook_name": f"{self.name}",
						"document_type": "Multi Channel Cadence",
						"doc_event": "on_update",
						"condition_type": "Filters",
						"is_active": 0,
						"filters": [
							{"fieldname": "cadence_name", "operator": "=", "value": self.name},
							{"fieldname": "status", "operator": "=", "value": "Provisioning"}
						]
					}).insert(ignore_permissions=True)
					self.db_set("reference_playbook", playbook.name)
					self.reference_playbook = playbook.name
			except Exception as e:
				frappe.log_error(title="Failed to create/link playbook for Cadence", message=str(e))

import json

def enqueue_lead_evaluation(doc, method):
	"""Enqueues the lead for cadence evaluation."""
	from frappe_controller.utils.background_jobs import enqueue

	enqueue(
		"frappe_cadence.cadence.doctype.cadence.cadence.evaluate_lead_for_cadences",
		queue="high",
		lead_name=doc.name
	)

def evaluate_cadence_for_leads(cadence_name):
	"""Evaluates a single Cadence against all leads."""
	try:
		cadence = frappe.get_doc("Cadence", cadence_name)
	except frappe.DoesNotExistError:
		frappe.log_error(title="Cadence evaluation failed", message=f"Cadence {cadence_name} does not exist.")
		return

	if not cadence.assign_condition_json:
		return

	# Fetch already enrolled leads
	enrolled_leads = frappe.get_all(
		"Multi Channel Cadence",
		filters={"cadence_name": cadence_name},
		pluck="recipient"
	)

	try:
		filters = json.loads(cadence.assign_condition_json)
		if not isinstance(filters, list):
			frappe.log_error(title="Invalid Cadence Assign Condition JSON", message="Filters must be a list.")
		else:
			# Append the exclusion filter
			if enrolled_leads:
				filters.append(["name", "not in", enrolled_leads])
			try:
				# Fetch leads directly matching the condition
				targeted_leads = frappe.get_all("CRM Lead", filters=filters, pluck="name")
				for lead_name in targeted_leads:
					add_lead_to_cadence(cadence, lead_name)
			except Exception as e:
				frappe.log_error(title="Error evaluating Cadence assignment JSON", message=str(e))
	except (json.JSONDecodeError, TypeError) as e:
		frappe.log_error(title="Invalid Cadence Assign Condition JSON", message=str(e))

def evaluate_lead_for_cadences(lead_name):
	"""Evaluates a single Lead against all Cadences."""
	try:
		lead_doc = frappe.get_doc("CRM Lead", lead_name)
	except frappe.DoesNotExistError:
		frappe.log_error(title="Lead evaluation failed", message=f"Lead {lead_name} does not exist.")
		return
		
	# Get cadences with condition set
	cadences = frappe.get_all(
		"Cadence",
		or_filters=[
			["assign_condition_json", "!=", ""],
			["assign_condition_json", "is", "set"]
		],
		pluck="name"
	)

	for cadence_name in cadences:
		cadence = frappe.get_doc("Cadence", cadence_name)

		# Skip if enrolled
		if frappe.db.exists("Multi Channel Cadence", {"cadence_name": cadence.name, "recipient": lead_name}):
			continue

		matched = False

		# JSON eval via DB
		if cadence.assign_condition_json:
			try:
				filters = json.loads(cadence.assign_condition_json)
				filters.append(["name", "=", lead_name])
				if frappe.get_all("CRM Lead", filters=filters, limit=1):
					matched = True
			except Exception as e:
				frappe.log_error(title="Error evaluating Cadence assignment JSON", message=str(e))

		if matched:
			add_lead_to_cadence(cadence, lead_name)

def add_lead_to_cadence(cadence, lead_name):
	# Check again to avoid race conditions
	if frappe.db.exists("Multi Channel Cadence", {"cadence_name": cadence.name, "recipient": lead_name}):
		return
		
	sender = determine_sender(cadence)
	
	try:
		email_cadence = frappe.new_doc("Multi Channel Cadence")
		email_cadence.cadence_name = cadence.name
		email_cadence.cadence_for = "CRM Lead"
		email_cadence.recipient = lead_name
		email_cadence.sender = sender
		email_cadence.save(ignore_permissions=True)
	except Exception as e:
		frappe.log_error(title="Failed to enroll lead in cadence", message=str(e))

def determine_sender(cadence):
	if not cadence.users:
		return cadence.owner or frappe.session.user
		
	user_ids = [u.user for u in cadence.users]

	if cadence.rule == "Round Robin":
		if not cadence.last_user or cadence.last_user not in user_ids:
			sender = user_ids[0]
		else:
			idx = user_ids.index(cadence.last_user)
			next_idx = (idx + 1) % len(user_ids)
			sender = user_ids[next_idx]
			
		cadence.db_set("last_user", sender)
		return sender
		
	elif cadence.rule == "Load Balancing":
		# Query to find the user with the fewest Multi Channel Cadences
		counts = frappe.db.sql(
			"""
			SELECT sender, COUNT(name) as cnt
			FROM `tabMulti Channel Cadence`
			WHERE sender IN %s AND docstatus != 2
			GROUP BY sender
			""", (tuple(user_ids),), as_dict=True
		)
		
		# Map counts to users
		user_counts = {u: 0 for u in user_ids}
		for c in counts:
			user_counts[c.sender] = c.cnt
			
		# Find user with minimum count
		sender = min(user_counts, key=user_counts.get)
		return sender
		
	return cadence.owner or frappe.session.user

def get_sequence_message(lead_name, sequence_name, step, test):
	"""
	Fetches the email body for the specified sequence and step.
	"""
	# 1. Find the Sequence Contact record
	# Note: Assuming 'reference_name' stores the Lead ID
	seq_contact = frappe.db.get_value("Sequence Contact",
		{"reference_name": lead_name, "sequence": sequence_name},
		"name"
	)
	
	if not seq_contact:
		return ""

	# 2. Fetch the content linked to this sequence contact and step
	content = frappe.db.get_value("Sequence Email",
		{"sequence_contact": seq_contact, "step": step, "test": test},
		"message"
	)
	
	return content or ""
