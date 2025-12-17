from typing import Dict, Any

def eligibility_agent(extracted_docs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Simple PoC rules:
    - if declared income is very low and family size > 1 => potentially eligible
    - if liabilities are huge relative to income => risk flag
    - if employment is unemployed => more likely eligible for support (but needs validation)
    """
    app = extracted_docs.get("APPLICATION_FORM", {}) or {}
    credit = extracted_docs.get("CREDIT_REPORT", {}) or {}

    income = app.get("declared_monthly_income")
    family = app.get("family_size")
    emp = (app.get("employment_status") or "").lower()

    liabilities = credit.get("total_liabilities")

    flags = []
    status = "UNKNOWN"

    if isinstance(liabilities, (int, float)) and isinstance(income, (int, float)) and income > 0:
        if liabilities > 12 * income:
            flags.append("HIGH_LIABILITY_BURDEN")

    if isinstance(income, (int, float)) and isinstance(family, (int, float)):
        if income <= 8000 and family >= 2:
            status = "POTENTIALLY_ELIGIBLE"
        elif income > 20000:
            status = "LIKELY_INELIGIBLE"
        else:
            status = "BORDERLINE"

    if "unemploy" in emp:
        flags.append("UNEMPLOYED")

    return {
        "eligibility_status": status,
        "risk_flags": flags
    }
