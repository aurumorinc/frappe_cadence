app_name = "frappe_campaign"
app_title = "Frappe Campaign"
app_publisher = "Aryan Singh"
app_description = "Open-Source Cold Outreach & Sales Engagement Automation"
app_email = "aquiveal@gmail.com"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "frappe_campaign",
# 		"logo": "/assets/frappe_campaign/logo.png",
# 		"title": "Frappe Campaign",
# 		"route": "/frappe_campaign",
# 		"has_permission": "frappe_campaign.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/frappe_campaign/css/frappe_campaign.css"
# app_include_js = "/assets/frappe_campaign/js/frappe_campaign.js"

# include js, css files in header of web template
# web_include_css = "/assets/frappe_campaign/css/frappe_campaign.css"
# web_include_js = "/assets/frappe_campaign/js/frappe_campaign.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "frappe_campaign/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "frappe_campaign/public/icons.svg"

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
jinja = {
	"methods": [
		"frappe_campaign.utils.jinja.get_sequence_message"
	]
}

# Installation
# ------------

# before_install = "frappe_campaign.install.before_install"
# after_install = "frappe_campaign.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "frappe_campaign.uninstall.before_uninstall"
# after_uninstall = "frappe_campaign.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "frappe_campaign.utils.before_app_install"
# after_app_install = "frappe_campaign.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "frappe_campaign.utils.before_app_uninstall"
# after_app_uninstall = "frappe_campaign.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "frappe_campaign.notifications.get_notification_config"

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
	"Email Template": {
		"before_save": [
			"frappe_campaign.utils.email_template.before_save"
		]
	},
	"Email Campaign": {
		"after_insert": "frappe_campaign.utils.crm_lead.sync_lead_campaign",
		"on_update": "frappe_campaign.utils.crm_lead.sync_lead_campaign",
		"on_trash": "frappe_campaign.utils.crm_lead.remove_lead_campaign"
	}
}

# Scheduled Tasks
# ---------------

scheduler_events = {
	"daily": [
		"frappe_campaign.utils.enrichment.check_and_mark_stale_enrichments"
	]
}


# Testing
# -------

# before_tests = "frappe_campaign.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "frappe_campaign.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "frappe_campaign.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "frappe_campaign.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["frappe_campaign.utils.before_request"]
# after_request = ["frappe_campaign.utils.after_request"]

# Job Events
# ----------
# before_job = ["frappe_campaign.utils.before_job"]
# after_job = ["frappe_campaign.utils.after_job"]

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
# 	"frappe_campaign.auth.validate"
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
	{"dt": "Custom Field", "filters": [["module", "in", ["Campaign", "CRM"]]]},
	{"dt": "Property Setter", "filters": [["module", "in", ["Campaign"]]]}
]
