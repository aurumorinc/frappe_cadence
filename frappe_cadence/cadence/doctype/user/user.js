frappe.ui.form.on("User", {
    refresh: function(frm) {
        frm.toggle_display("bio", frappe.session.user === frm.doc.name);
    }
});
