// Copyright (c) 2021, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Cadence", {
	refresh: function (frm) {
		if (frm.is_new()) {
			frm.toggle_display("cadence_code", false);
			frm.toggle_reqd("cadence_code", 0);
			frm.toggle_display("naming_series", true);
		} else {
			frm.toggle_display("naming_series", false);
			frm.add_custom_button(
				__("View Leads"),
				function () {
					frappe.route_options = { utm_source: "Cadence", utm_campaign: frm.doc.name };
					frappe.set_route("List", "CRM Lead");
				},
				"fa fa-list",
				true
			);
		}
	},
});
