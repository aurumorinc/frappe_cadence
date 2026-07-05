import frappe
from typing import List, Dict, Any

@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_crm_leads(doctype: str, txt: str, searchfield: str, start: int, page_len: int, filters: Dict[str, Any]) -> List[List[str]]:
    template_name = filters.get("template_name")
    
    if not template_name:
        return []

    # Get all Cadences that use this template
    cadences = frappe.get_all(
        "Cadence Multi Channel Schedule",
        filters={"reference_name": template_name},
        pluck="parent"
    )
    
    if not cadences:
        return []

    # Get all leads from MCC records associated with these cadences
    # where status is not Provisioning and not Error
    
    mcc_doctype = frappe.qb.DocType("Multi Channel Cadence")
    
    query = (
        frappe.qb.from_(mcc_doctype)
        .select(mcc_doctype.recipient)
        .distinct()
        .where(
            (mcc_doctype.cadence_name.isin(cadences)) &
            (mcc_doctype.status.notin(['Provisioning', 'Error']))
        )
    )

    if txt:
        query = query.where(mcc_doctype.recipient.like(f"%{txt}%"))

    query = query.limit(page_len).offset(start)
    
    records = query.run()
    
    return records
