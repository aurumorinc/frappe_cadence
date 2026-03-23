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
		self.update_email_campaigns()

	def update_email_campaigns(self):
		email_campaigns = frappe.get_all("Email Campaign", filters={"campaign_name": self.name}, pluck="name")
		
		# Map existing schedules from this campaign
		master_schedules = []
		template_map = {}
		for row in self.get("campaign_schedules"):
			master_schedules.append({
				"email_template": row.email_template,
				"send_after_days": row.send_after_days,
				"subject_apollo_id": row.subject_apollo_id,
				"response_apollo_id": row.response_apollo_id,
				"reference_doc": row.reference_doc,
				"reference_docname": row.reference_docname
			})
			template_map[row.email_template] = {
				"subject_apollo_id": row.subject_apollo_id,
				"response_apollo_id": row.response_apollo_id
			}

		for ec_name in email_campaigns:
			ec = frappe.get_doc("Email Campaign", ec_name)
			dirty = False
			
			# Check for apollo id updates
			for ec_row in ec.get("campaign_email_schedules"):
				if ec_row.email_template in template_map:
					if not ec_row.reference_docname:
						data = template_map[ec_row.email_template]
						if ec_row.subject_apollo_id != data["subject_apollo_id"]:
							ec_row.subject_apollo_id = data["subject_apollo_id"]
							dirty = True
						if ec_row.response_apollo_id != data["response_apollo_id"]:
							ec_row.response_apollo_id = data["response_apollo_id"]
							dirty = True
							
			# Check for new schedules added to the master campaign
			existing_keys = {(r.email_template, r.send_after_days) for r in ec.get("campaign_email_schedules")}
			new_rows_added = False
			
			for m_row in master_schedules:
				key = (m_row["email_template"], m_row["send_after_days"])
				if key not in existing_keys:
					ec.append("campaign_email_schedules", m_row)
					dirty = True
					new_rows_added = True
					
			if new_rows_added and ec.status != "Draft":
				ec.status = "Draft"
			
			if dirty:
				ec.save(ignore_permissions=True)

	def autoname(self):
		if frappe.defaults.get_global_default("campaign_naming_by") != "Naming Series":
			self.name = self.campaign_name
		else:
			set_name_by_naming_series(self)
