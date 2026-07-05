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
		from frappe_cadence.cadence.doctype.channel_cadence_provider.channel_cadence_provider import ChannelCadenceProvider
		from frappe_cadence.cadence.doctype.cadence_multi_channel_schedule.cadence_multi_channel_schedule import CadenceMultiChannelSchedule

		assign_condition: DF.Code | None
		assign_condition_json: DF.Code | None
		cadence_code: DF.Data
		cadence_name: DF.Data
		cadence_schedules: DF.Table[CadenceMultiChannelSchedule]
		provider: DF.Table[ChannelCadenceProvider]
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
		self.ensure_playbook()
		frappe.enqueue(
			"frappe_cadence.cadence.doctype.cadence.cadence.update_sequences",
			queue="long",
			cadence_name=self.name,
			now=frappe.flags.in_test
		)
		frappe.enqueue(
			"frappe_cadence.cadence.doctype.cadence.cadence.evaluate_cadence_for_leads",
			queue="long",
			cadence_name=self.name,
			now=frappe.flags.in_test
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
						"doc_event": "Save",
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

def update_sequences(cadence_name):
	if not frappe.db.exists("DocType", "Sequence"):
		return
	try:
		sequences = frappe.get_all("Sequence", filters={"cadence": cadence_name}, pluck="name")
		for seq_name in sequences:
			seq = frappe.get_doc("Sequence", seq_name)
			seq.populate_sequence_steps()
			seq.save(ignore_permissions=True)
	except Exception as e:
		frappe.log_error(title="Failed to update sequences for Cadence", message=str(e))

import json
from frappe.utils.safe_exec import safe_eval

def enqueue_lead_evaluation(doc, method):
	"""Enqueues the lead for cadence evaluation."""
	frappe.enqueue(
		"frappe_cadence.cadence.doctype.cadence.cadence.evaluate_lead_for_cadences",
		queue="short",
		lead_name=doc.name,
		now=frappe.flags.in_test
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
		
	try:
		filters = json.loads(cadence.assign_condition_json)
	except (json.JSONDecodeError, TypeError) as e:
		frappe.log_error(title="Invalid Cadence Assign Condition JSON", message=str(e))
		return
	
	if not isinstance(filters, list):
		frappe.log_error(title="Invalid Cadence Assign Condition JSON", message="Filters must be a list.")
		return
		
	# Build subquery to exclude already enrolled leads
	email_cadence = frappe.qb.DocType("Multi Channel Cadence")
	subquery = frappe.qb.from_(email_cadence).select(email_cadence.recipient).where(email_cadence.cadence_name == cadence_name)

	# Append the exclusion filter
	filters.append(["name", "not in", subquery])

	try:
		# Fetch leads directly matching the condition
		targeted_leads = frappe.get_all("CRM Lead", filters=filters, pluck="name")
	except Exception as e:
		frappe.log_error(title="Error evaluating Cadence assignment", message=str(e))
		return
		
	for lead_name in targeted_leads:
		add_lead_to_cadence(cadence, lead_name)

def evaluate_lead_for_cadences(lead_name):
	"""Evaluates a single Lead against all Cadences."""
	try:
		lead_doc = frappe.get_doc("CRM Lead", lead_name)
	except frappe.DoesNotExistError:
		frappe.log_error(title="Lead evaluation failed", message=f"Lead {lead_name} does not exist.")
		return
		
	# Get cadences with either condition set
	cadences = frappe.get_all(
		"Cadence",
		or_filters=[
			["assign_condition_json", "!=", ""],
			["assign_condition_json", "is", "set"],
			["assign_condition", "!=", ""],
			["assign_condition", "is", "set"]
		],
		pluck="name"
	)

	for cadence_name in cadences:
		cadence = frappe.get_doc("Cadence", cadence_name)
		
		# Skip if enrolled
		if frappe.db.exists("Multi Channel Cadence", {"cadence_name": cadence.name, "recipient": lead_name}):
			continue
			
		matched = False
		
		# Try JSON eval via DB
		if cadence.assign_condition_json:
			try:
				filters = json.loads(cadence.assign_condition_json)
				filters.append(["name", "=", lead_name])
				if frappe.get_all("CRM Lead", filters=filters, limit=1):
					matched = True
			except Exception as e:
				frappe.log_error(title="Error evaluating Cadence assignment JSON", message=str(e))
				
		# Try python eval
		if not matched and cadence.assign_condition:
			try:
				matched = frappe.safe_eval(cadence.assign_condition, None, {"doc": lead_doc})
			except Exception as e:
				frappe.log_error(title="Error evaluating Cadence assignment Python", message=str(e))
				
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
		email_cadence.start_date = frappe.utils.nowdate()
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
		counts = frappe.get_all(
			"Multi Channel Cadence",
			filters={"sender": ["in", user_ids], "docstatus": ["!=", 2]},
			fields=["sender", "count(name) as cnt"],
			group_by="sender"
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
