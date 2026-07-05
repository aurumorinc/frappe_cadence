frappe.ui.form.on("LinkedIn Template", {
	setup: function(frm) {
		frm.set_query("reference_name", "annotations", function(doc, cdt, cdn) {
			return {
				query: "frappe_cadence.utils.enrichment.get_crm_leads",
				filters: {
					"template_name": doc.name,
					"template_type": doc.doctype
				}
			};
		});
	},
	refresh: function(frm) {
		frm.add_custom_button(__("Optimize"), function() {
			frappe.call({
				method: "frappe_cadence.utils.sift.optimize",
				args: {
					template_doctype: frm.doc.doctype,
					template_name: frm.doc.name
				},
				callback: function(r) {
					if (!r.exc) {
						frm.reload_doc();
					}
				}
			});
		});
		frm.add_custom_button(__("Predict"), function() {
			frappe.call({
				method: "frappe_cadence.utils.sift.predict",
				args: {
					template_doctype: frm.doc.doctype,
					template_name: frm.doc.name
				},
				callback: function(r) {
					if (!r.exc) {
						frm.reload_doc();
					}
				}
			});
		});
	}
});
