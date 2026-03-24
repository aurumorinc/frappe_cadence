# Copyright (c) 2021, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.model.naming import set_name_by_naming_series


class Campaign(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		from erpnext.crm.doctype.campaign_email_schedule.campaign_email_schedule import (
			CampaignEmailSchedule,
		)

		campaign_name: DF.Data
		campaign_schedules: DF.Table[CampaignEmailSchedule]
		description: DF.Text | None
		naming_series: DF.Literal["SAL-CAM-.YYYY.-"]
	# end: auto-generated types

	def after_insert(self):
		if frappe.db.exists("UTM Campaign", self.campaign_name):
			mc = frappe.get_doc("UTM Campaign", self.campaign_name)
		else:
			mc = frappe.new_doc("UTM Campaign")
			mc.name = self.campaign_name
		mc.campaign_description = self.description
		mc.crm_campaign = self.campaign_name
		mc.save(ignore_permissions=True)

	def on_change(self):
		if frappe.db.exists("UTM Campaign", self.campaign_name):
			mc = frappe.get_doc("UTM Campaign", self.campaign_name)
		else:
			mc = frappe.new_doc("UTM Campaign")
			mc.name = self.campaign_name
		mc.campaign_description = self.description
		mc.crm_campaign = self.campaign_name
		mc.save(ignore_permissions=True)

	def on_update(self):
		frappe.enqueue(
			"frappe_campaign.campaign.doctype.campaign.campaign.update_sequences",
			queue="long",
			campaign_name=self.name,
		)
		frappe.enqueue(
			"frappe_campaign.campaign.doctype.campaign.campaign.update_email_campaigns",
			queue="long",
			campaign_name=self.name,
		)

def update_sequences(campaign_name):
	sequences = frappe.get_all("Sequence", filters={"campaign": campaign_name}, pluck="name")
	for seq_name in sequences:
		seq = frappe.get_doc("Sequence", seq_name)
		seq.populate_sequence_steps()
		seq.save(ignore_permissions=True)

def update_email_campaigns(campaign_name):
	campaign_doc = frappe.get_doc("Campaign", campaign_name)
	email_campaigns = frappe.get_all("Email Campaign", filters={"campaign_name": campaign_name}, pluck="name")
	
	# Map existing schedules from this campaign
	master_schedules = []
	for row in campaign_doc.get("campaign_schedules"):
		master_schedules.append({
			"idx": row.idx,
			"email_template": row.email_template,
			"send_after_days": row.send_after_days,
			"reference_doc": row.reference_doc,
			"reference_docname": row.reference_docname
		})

	for ec_name in email_campaigns:
		ec = frappe.get_doc("Email Campaign", ec_name)
		
		# Get existing email campaign schedules
		ec_schedules = ec.get("campaign_email_schedules")
		
		# Clear existing list to rebuild it matched to the campaign
		ec.set("campaign_email_schedules", [])

		new_rows_added = False

		for m_row in master_schedules:
			# Look for an existing row in ec_schedules with the same idx to preserve apollo IDs if present
			existing_row = next((r for r in ec_schedules if r.idx == m_row["idx"]), None)
			
			if not existing_row:
				new_rows_added = True

			new_row = ec.append("campaign_email_schedules", {
				"idx": m_row["idx"],
				"email_template": m_row["email_template"],
				"send_after_days": m_row["send_after_days"],
				"reference_doc": m_row["reference_doc"],
				"reference_docname": m_row["reference_docname"]
			})

		if new_rows_added and ec.status != "Draft":
			ec.status = "Draft"
		
		ec.save(ignore_permissions=True)

	def autoname(self):
		if frappe.defaults.get_global_default("campaign_naming_by") != "Naming Series":
			self.name = self.campaign_name
		else:
			set_name_by_naming_series(self)
