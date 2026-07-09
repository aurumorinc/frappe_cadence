frappe.ui.form.on("User", {
	refresh: function (frm) {
		// Only show bio if the logged-in user is viewing their own profile
		frm.toggle_display("bio", frappe.session.user === frm.doc.name);
	}
});
