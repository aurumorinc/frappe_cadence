import frappe
import json
from frappe_campaign.crm_lead import get as get_crm_leads

@frappe.whitelist()
def get(filters=None, fields=None, limit=None):
    """
    Fetches leads matching the `filters` criteria, 
    and returns the unique organizations for those leads.
    """
    # Parse the incoming fields from JSON string
    if isinstance(fields, str):
        fields = json.loads(fields)
        
    if not fields:
        fields = ["name"]
        
    limit_kwargs = {}
    if limit is not None:
        try:
            limit_kwargs["limit_page_length"] = int(limit)
        except ValueError:
            pass
        
    # We use our custom get_crm_leads method to fetch the leads with 'organization'
    # By passing the 'filters', it handles standard lead filters plus our custom 'exclude_campaign'
    leads = get_crm_leads(filters=filters, fields=["organization"], limit=limit)
    
    # Extract unique organizations
    org_names = list(set([lead.get("organization") for lead in leads if lead.get("organization")]))
    
    if not org_names:
        return []
        
    # Fetch the actual organization records
    organizations = frappe.get_all(
        "CRM Organization", 
        filters={"name": ("in", org_names)}, 
        fields=fields,
        **limit_kwargs
    )
    
    return organizations
