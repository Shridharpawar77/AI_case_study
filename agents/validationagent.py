from typing import Dict, Any, List, Tuple
import re


CRITICAL_FIELDS = {
    "APPLICATION_FORM": ["applicant_name", "declared_monthly_income", "family_size", "employment_status"],
    "EMIRATES_ID": ["full_name", "emirates_id"],
}


def _normalize_text(s: Any) -> str:
    if s is None:
        return ""
    s = str(s).strip().lower()
    # remove extra spaces + punctuation to make matching tolerant
    s = re.sub(r"[\s]+", " ", s)
    s = re.sub(r"[^\w\s]", "", s)
    return s


def _count_by_severity(issues: List[dict]) -> Tuple[int, int, int]:
    high = sum(1 for i in issues if i.get("severity") == "HIGH")
    med = sum(1 for i in issues if i.get("severity") == "MEDIUM")
    low = sum(1 for i in issues if i.get("severity") == "LOW")
    return high, med, low


def validation_agent(extracted_docs: Dict[str, Any]) -> Dict[str, Any]:
    """
    extracted_docs example:
    {
      "APPLICATION_FORM": {...},
      "EMIRATES_ID": {...},
      "BANK_STATEMENT": {...},
      "CREDIT_REPORT": {...},
      "RESUME": {...}
    }
    """

    issues: List[dict] = []

    app = extracted_docs.get("APPLICATION_FORM", {}) or {}
    eid = extracted_docs.get("EMIRATES_ID", {}) or {}
    bank = extracted_docs.get("BANK_STATEMENT", {}) or {}
    credit = extracted_docs.get("CREDIT_REPORT", {}) or {}
    resume = extracted_docs.get("RESUME", {}) or {}

    # ---------------------------
    # 1) Missing critical fields
    # ---------------------------
    for dt, fields in CRITICAL_FIELDS.items():
        d = extracted_docs.get(dt, {}) or {}
        for f in fields:
            if d.get(f) in (None, "", [], {}):
                issues.append({
                    "type": "MISSING_FIELD",
                    "severity": "HIGH",
                    "description": f"Missing required field '{f}' in {dt}"
                })

    # ---------------------------
    # 2) Name consistency (NEW) - HIGH
    # ---------------------------
    app_name = _normalize_text(app.get("applicant_name"))
    eid_name = _normalize_text(eid.get("full_name"))

    if app_name and eid_name and app_name != eid_name:
        issues.append({
            "type": "NAME_MISMATCH",
            "severity": "HIGH",
            "description": "Applicant name differs between Application Form and Emirates ID"
        })

    # ---------------------------
    # 3) Address mismatch (existing logic)
    # ---------------------------
    app_addr = _normalize_text(app.get("address"))
    eid_addr = _normalize_text(eid.get("address"))

    if app_addr and eid_addr and app_addr != eid_addr:
        issues.append({
            "type": "ADDRESS_MISMATCH",
            "severity": "HIGH",
            "description": "Address differs between Application Form and Emirates ID"
        })

    # ---------------------------
    # 4) Address missing in EID (NEW) - LOW or MEDIUM
    # ---------------------------
    # If application has address but EID has no address, it's a completeness gap.
    # Keep LOW in PoC; switch to MEDIUM if you want stricter workflow.
    if app_addr and not eid_addr:
        issues.append({
            "type": "ADDRESS_MISSING_IN_EID",
            "severity": "LOW",
            "description": "Emirates ID did not provide an address; address proof may be required"
        })

    # ---------------------------
    # 5) Income consistency (existing logic)
    # ---------------------------
    declared_income = app.get("declared_monthly_income")
    bank_income = bank.get("monthly_income")

    if isinstance(declared_income, (int, float)) and isinstance(bank_income, (int, float)) and declared_income > 0:
        diff = abs(declared_income - bank_income)
        # mismatch if >20%
        if diff > 0.2 * declared_income:
            issues.append({
                "type": "INCOME_MISMATCH",
                "severity": "HIGH",
                "description": "Declared income significantly differs from bank statement"
            })

    # ---------------------------
    # 6) Liabilities sanity (existing logic)
    # ---------------------------
    total_liab = credit.get("total_liabilities")
    if isinstance(total_liab, (int, float)) and total_liab < 0:
        issues.append({
            "type": "INVALID_LIABILITIES",
            "severity": "MEDIUM",
            "description": "Total liabilities cannot be negative"
        })

    # ---------------------------
    # 7) Employer mismatch (NEW) - MEDIUM
    # ---------------------------
    # We check mismatch between:
    # - BANK_STATEMENT.employer_name (salary narration)
    # - APPLICATION_FORM.employer_name (declared)
    # - RESUME.current_employer (latest)
    bank_emp = _normalize_text(bank.get("employer_name"))
    form_emp = _normalize_text(app.get("employer_name"))
    resume_emp = _normalize_text(resume.get("current_employer"))

    # If we have bank employer + either form/resume employer and they disagree
    if bank_emp:
        if form_emp and bank_emp != form_emp:
            issues.append({
                "type": "EMPLOYER_MISMATCH",
                "severity": "MEDIUM",
                "description": "Employer differs between bank statement and application form"
            })
        if resume_emp and bank_emp != resume_emp:
            issues.append({
                "type": "EMPLOYER_MISMATCH",
                "severity": "MEDIUM",
                "description": "Employer differs between bank statement and resume"
            })

    # ---------------------------
    # Summary + decision hint
    # ---------------------------
    high, med, low = _count_by_severity(issues)

    decision_hint = "PASS"
    if high > 0:
        decision_hint = "NEEDS_REVIEW"

    return {
        "issues": issues,
        "validation_summary": {
            "high": high,
            "medium": med,
            "low": low,
            "total": len(issues),
            "decision_hint": decision_hint
        }
    }
