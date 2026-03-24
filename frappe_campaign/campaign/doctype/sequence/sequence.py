import frappe
from frappe.model.document import Document

class Sequence(Document):
	def validate(self):
		self.populate_sequence_steps()

	def populate_sequence_steps(self):
		if not self.campaign:
			return

		campaign_doc = frappe.get_doc("Campaign", self.campaign)
		expected_steps = len(campaign_doc.get("campaign_schedules"))
		
		# If the table is empty or smaller than expected, clear and rebuild to match exactly
		# or just append missing ones. Since they map to idx, let's ensure we have exactly `expected_steps` rows.
		current_steps = self.get("sequence_steps")
		existing_steps = len(current_steps)

		if existing_steps < expected_steps:
			for i in range(existing_steps, expected_steps):
				self.append("sequence_steps", {
					"subject_custom_field_id": "",
					"response_custom_field_id": ""
				})
		elif existing_steps > expected_steps:
			# Remove extra rows from the end
			for i in range(existing_steps - 1, expected_steps - 1, -1):
				self.remove(current_steps[i])
