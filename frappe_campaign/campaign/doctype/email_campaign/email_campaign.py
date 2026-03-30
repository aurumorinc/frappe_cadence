# Copyright (c) 2019, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from frappe.utils import add_days, getdate, today

class EmailCampaign(Document):
	def validate(self):
		self.set_date()
		# checking if email is set for lead. Not checking for contact as email is a mandatory field for contact.
		if self.email_campaign_for == "CRM Lead":
			self.validate_lead()
		self.validate_email_campaign_already_exists()
		# status is handled via lifecycle methods

	def set_date(self):
		if self.is_new() or self.has_value_changed("start_date"):
			if getdate(self.start_date) < getdate(today()):
				frappe.throw(_("Start Date cannot be before the current date"))

		if self.status in ["Completed", "Unsubscribed"]:
			return

		# set the end date as start date + max(send after days) in campaign schedule
		campaign = frappe.get_cached_doc("Campaign", self.campaign_name)
		send_after_days = [entry.send_after_days for entry in campaign.get("campaign_schedules")]

		if not send_after_days:
			frappe.throw(
				_("Please set up the Campaign Schedule in the Campaign {0}").format(self.campaign_name)
			)

		self.end_date = add_days(getdate(self.start_date), max(send_after_days))

	def before_save(self):
		if self.has_value_changed("status"):
			if self.status == "In Progress":
				self.start_date = today()
				self.set_date()
			elif self.status in ["Completed", "Unsubscribed"]:
				self.end_date = today()

	def validate_lead(self):
		lead_email_id = frappe.db.get_value("CRM Lead", self.recipient, "email")
		if not lead_email_id:
			lead_name = frappe.db.get_value("CRM Lead", self.recipient, "lead_name")
			frappe.throw(_("Please set an email id for the Lead {0}").format(lead_name))

	def validate_email_campaign_already_exists(self):
		email_campaign_exists = frappe.db.exists(
			"Email Campaign",
			{
				"campaign_name": self.campaign_name,
				"recipient": self.recipient,
				"status": ("in", ["In Progress", "Scheduled"]),
				"name": ("!=", self.name),
			},
		)
		if email_campaign_exists:
			frappe.throw(
				_("The Campaign '{0}' already exists for the {1} '{2}'").format(
					self.campaign_name, self.email_campaign_for, self.recipient
				)
			)

	def after_insert(self):
		# 1. Frappe natively copies the campaign_schedules from the parent Campaign into the local campaign_email_schedules child table.
		campaign = frappe.get_doc("Campaign", self.campaign_name)
		campaign_schedules = campaign.get("campaign_schedules") or []
		for entry in campaign_schedules:
			self.append("campaign_email_schedules", {
				"email_template": entry.email_template,
				"send_after_days": entry.send_after_days,
				"subject_apollo_id": entry.subject_apollo_id,
				"response_apollo_id": entry.response_apollo_id,
				"reference_doc": entry.reference_doc,
				"reference_docname": entry.reference_docname
			})
		
		# We must save after appending
		self.save()

	def on_update(self):
		# check if we need to generate prompts or just render
		requires_generation = False
		steps_to_generate = []
		context = {}
		if self.email_campaign_for:
			try:
				context = {"doc": frappe.get_doc(self.email_campaign_for, self.recipient)}
			except Exception:
				pass

		for schedule in self.get("campaign_email_schedules"):
			if not schedule.subject or not schedule.response:
				template = frappe.get_doc("Email Template", schedule.email_template)
				
				if getattr(template, "status", "Enabled") == "Prompt":
					requires_generation = True
					steps_to_generate.append(schedule.idx)
				else:
					# Standard Jinja Template
					if getattr(template, "subject", None):
						schedule.subject = frappe.render_template(template.subject, context)
					if getattr(template, "response_", None):
						schedule.response = frappe.render_template(template.response_, context)
					elif getattr(template, "response", None):
						schedule.response = frappe.render_template(template.response, context)
					
		if requires_generation and self.status != "Draft":
			self.db_set("status", "Draft", update_modified=False)
			
			# Offload the heavy payload creation and queuing to the Agent utility asynchronously
			from frappe_campaign.utils.agent import queue_generation_task
			for idx in steps_to_generate:
				frappe.enqueue(
					queue_generation_task,
					queue="short",
					campaign_name=self.name,
					schedule_idx=idx
				)
		elif requires_generation and self.status == "Draft":
			# Still offload if it's already in draft and generation is still required
			# Offload the heavy payload creation and queuing to the Agent utility asynchronously
			from frappe_campaign.utils.agent import queue_generation_task
			for idx in steps_to_generate:
				frappe.enqueue(
					queue_generation_task,
					queue="short",
					campaign_name=self.name,
					schedule_idx=idx
				)
				
		elif not requires_generation and self.status == "Draft":
			all_filled = all((s.subject and s.response) for s in self.get("campaign_email_schedules"))
			if all_filled:
				self.db_set("status", "Scheduled", update_modified=False)

		if self.status == "Scheduled":
			pass


# called from hooks on doc_event Email Unsubscribe
def unsubscribe_recipient(unsubscribe, method):
	if unsubscribe.reference_doctype == "Email Campaign":
		frappe.db.set_value("Email Campaign", unsubscribe.reference_name, {
			"status": "Unsubscribed",
			"end_date": today()
		})

def mark_campaign_completed(email_campaign_name):
	frappe.db.set_value("Email Campaign", email_campaign_name, {
		"status": "Completed",
		"end_date": today()
	})

def requeue_timed_out_generations():
	# Sweeper Job to re-queue campaigns stuck in Generating state (status = '') for more than 60 minutes
	# Allowing Convoy enough time (10 retries, ~50 mins) to finish before we assume the message is dead.
	from frappe.utils import add_to_date, now_datetime

	threshold = add_to_date(now_datetime(), minutes=-60)

	# Fetch Email Campaigns that require generation but haven't been updated in 60 mins
	timed_out_campaigns = frappe.get_all(
		"Email Campaign",
		filters={
			"status": "Draft",
			"modified": ["<", threshold]
		},
		pluck="name"
	)

	for campaign_name in timed_out_campaigns:
		doc = frappe.get_doc("Email Campaign", campaign_name)
		# A simple save will trigger the on_update hooks, which will fire the Generation Webhook again
		doc.save(ignore_permissions=True)