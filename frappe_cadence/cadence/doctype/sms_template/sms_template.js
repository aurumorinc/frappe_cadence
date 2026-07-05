frappe.ui.form.on('SMS Template', {
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
    }
});