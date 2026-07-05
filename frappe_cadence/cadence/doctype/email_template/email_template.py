import frappe

def before_save(doc, method):
	if doc.status == "Disabled":
		doc.enabled = 0
	else:
		doc.enabled = 1
