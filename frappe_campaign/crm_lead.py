import frappe
import json

@frappe.whitelist()
def get(filters=None, fields=None, limit=None):
    if isinstance(filters, str):
        filters = json.loads(filters)
    if isinstance(fields, str):
        fields = json.loads(fields)
        
    if not filters:
        filters = []
    if not fields:
        fields = ["name"]
        
    limit_kwargs = {}
    if limit is not None:
        try:
            limit_kwargs["limit_page_length"] = int(limit)
        except ValueError:
            pass
        
    standard_filters = []
    excluded_campaigns = []
    
    if isinstance(filters, dict):
        standard_filters = filters
    elif isinstance(filters, list):
        for f in filters:
            if isinstance(f, list) and len(f) >= 3:
                # Parse Frappe's filter format
                doctype = f[0] if len(f) == 4 else None
                fieldname = f[1] if len(f) == 4 else f[0]
                operator = f[2] if len(f) == 4 else f[1]
                value = f[3] if len(f) == 4 else f[2]
                
                # Intercept the CRM Lead Campaign exclusion filter
                # We ignore fieldname (whether it is 'name' or 'campaign_name')
                # and assume the value contains the campaign IDs to exclude.
                if doctype == "CRM Lead Campaign" and operator.lower() in ("not in", "!="):
                    if isinstance(value, list):
                        excluded_campaigns.extend(value)
                    else:
                        excluded_campaigns.append(value)
                    continue
            standard_filters.append(f)
            
    # We need "name" in fields to filter excluded_campaigns
    added_name_field = False
    if excluded_campaigns and "name" not in fields and "*" not in fields:
        fields.append("name")
        added_name_field = True
            
    # Fetch leads using standard Frappe logic
    leads = frappe.get_all("CRM Lead", filters=standard_filters, fields=fields, **limit_kwargs)
    
    # Apply custom exclusion logic
    if excluded_campaigns:
        campaign_leads = frappe.get_all(
            "CRM Lead Campaign", 
            filters={"campaign_name": ("in", excluded_campaigns)}, 
            pluck="parent"
        )
        if campaign_leads:
            leads = [lead for lead in leads if lead.get("name") not in campaign_leads]
            
        # Clean up the "name" field if we added it just for filtering
        if added_name_field:
            for lead in leads:
                lead.pop("name", None)
            
    return leads
