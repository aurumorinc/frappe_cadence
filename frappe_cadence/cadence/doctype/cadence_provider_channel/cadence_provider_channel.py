# Copyright (c) 2026, Aryan Singh and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class CadenceProviderChannel(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		channel: DF.Literal["Email", "LinkedIn", "WhatsApp", "SMS", "Call"]
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		priority: DF.Int
		reference_cadence_provider: DF.Link
	# end: auto-generated types

	pass
