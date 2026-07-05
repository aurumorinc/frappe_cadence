# Copyright (c) 2024, Roo and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import add_months, now_datetime, get_datetime

class History(Document):
	pass

def check_and_mark_stale():
	"""
	Scheduled job to mark CRM Lead and CRM Organization records as 'Stale'
	if their latest enrichment history is older than 3 months.
	"""
	three_months_ago = add_months(now_datetime(), -3)
	
	for doctype in ["CRM Lead", "CRM Organization"]:
		# Fetch records that are currently 'Enriched' or 'Partial'
		# We only care about those that were successfully enriched at some point.
		records = frappe.get_all(doctype, filters={
			"enrichment_status": ["in", ["Enriched", "Partial"]]
		}, fields=["name"])
		
		for record in records:
			# Find the newest history record for this document
			latest_history = frappe.get_all("History",
				filters={
					"reference_doctype": doctype,
					"reference_name": record.name
				},
				fields=["creation"],
				order_by="creation desc",
				limit=1
			)
			
			# If the newest history record is older than 3 months, mark the parent as Stale
			if latest_history and get_datetime(latest_history[0].creation) < three_months_ago:
				frappe.db.set_value(doctype, record.name, "enrichment_status", "Stale")
				# Optimization: use db_set if no hooks are needed,
				# but set_value is safer for standard field updates.
				# frappe.db.commit() # Usually handled by the scheduler container
