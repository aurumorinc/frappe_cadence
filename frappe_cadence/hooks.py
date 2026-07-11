app_name = "frappe_cadence"
app_title = "Frappe Cadence"
app_publisher = "Aurumor"
app_description = "Open-Source Cold Outreach & Sales Engagement Automation"
app_email = "hello@aurumor.com"
app_license = "mit"

# Apps
# ------------------

required_apps = ["frappe_controller", "frappe_playbook", "crm"]

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "frappe_cadence",
# 		"logo": "/assets/frappe_cadence/logo.png",
# 		"title": "Frappe Cadence",
# 		"route": "/frappe_cadence",
# 		"has_permission": "frappe_cadence.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/frappe_cadence/css/frappe_cadence.css"
# app_include_js = "/assets/frappe_cadence/js/frappe_cadence.js"

# include js, css files in header of web template
# web_include_css = "/assets/frappe_cadence/css/frappe_cadence.css"
# web_include_js = "/assets/frappe_cadence/js/frappe_cadence.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "frappe_cadence/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
doctype_js = {
    "Email Template": "cadence/doctype/email_template/email_template.js",
    "User": "cadence/doctype/user/user.js"
}
doctype_list_js = {"Communication" : "cadence/doctype/communication/communication_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "frappe_cadence/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": [
# 		"frappe_cadence.cadence.doctype.cadence.cadence.get_sequence_message"
# 	]
# }

# Installation
# ------------

# before_install = "frappe_cadence.install.before_install"
# after_install = "frappe_cadence.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "frappe_cadence.uninstall.before_uninstall"
# after_uninstall = "frappe_cadence.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "frappe_cadence.utils.before_app_install"
# after_app_install = "frappe_cadence.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "frappe_cadence.utils.before_app_uninstall"
# after_app_uninstall = "frappe_cadence.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "frappe_cadence.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	"User": {
		"validate": "frappe_cadence.cadence.doctype.user.user.validate_bio"
	},
	"Email Template": {
		"before_save": [
			"frappe_cadence.cadence.doctype.email_template.email_template.before_save"
		]
	},
	"Email Cadence": {
		"after_insert": "frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.sync_lead_cadence",
		"on_update": "frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.sync_lead_cadence",
		"on_trash": "frappe_cadence.cadence.doctype.multi_channel_cadence.multi_channel_cadence.remove_lead_cadence"
	},
	"CRM Lead": {
		"on_update": "frappe_cadence.cadence.doctype.cadence.cadence.enqueue_lead_evaluation"
	},
	"Communication": {
		"after_insert": "frappe_cadence.cadence.doctype.communication.communication.on_communication_create",
		"on_update": "frappe_cadence.cadence.doctype.communication.communication.on_communication_update"
	},
	"Playbook Execution": {
		"on_update": "frappe_cadence.cadence.doctype.playbook_execution.playbook_execution.on_update"
	}
}

# Scheduled Tasks
# ---------------

scheduler_events = {}

# Controller Events
# -----------------

controller_events = {
	"frappe_cadence.cadence.multi_channel_cadence.process_cadence_step": {
		"rate_limit_per_minute": 50,
		"retries": 3,
		"timeout": 300
	}
}

# Testing
# -------

# before_tests = "frappe_cadence.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "frappe_cadence.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "frappe_cadence.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "frappe_cadence.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["frappe_cadence.utils.before_request"]
# after_request = ["frappe_cadence.utils.after_request"]

# Job Events
# ----------
# before_job = ["frappe_cadence.utils.before_job"]
# after_job = ["frappe_cadence.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"frappe_cadence.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
export_python_type_annotations = True

# Require all whitelisted methods to have type annotations
require_type_annotated_api_methods = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []

fixtures = [
	{"dt": "Custom Field", "filters": [["module", "in", ["Cadence", "CRM"]]]},
	{"dt": "Property Setter", "filters": [["module", "in", ["Cadence"]]]}
]
