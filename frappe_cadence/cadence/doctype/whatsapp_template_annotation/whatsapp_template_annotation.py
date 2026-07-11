# Copyright (c) 2026, Aurumor and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class WhatsappTemplateAnnotation(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		feedback: DF.TextEditor | None
		output: DF.TextEditor | None
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		reference_doctype: DF.Link | None
		reference_name: DF.DynamicLink | None
		score: DF.Float
		sender: DF.Link | None
	# end: auto-generated types

	pass
