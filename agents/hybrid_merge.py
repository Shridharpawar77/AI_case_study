from typing import Any, Dict, List, Tuple
import hashlib

SEVERITY_RANK = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}


def _norm(s: Any) -> str:
    if s is None:
        return ""
    return str(s).strip().lower()


def _issue_key(issue: Dict[str, Any]) -> str:
    """
    Create a stable key for de-duplication across rule + LLM issues.
    Uses type + (optional) field + normalized description.
    """
    t = _norm(issue.get("type") or issue.get("code") or "")
    f = _norm(issue.get("field") or "")
    desc = _norm(issue.get("description") or issue.get("message") or "")
    base = f"{t}|{f}|{desc}"
    return hashlib.md5(base.encode("utf-8")).hexdigest()


def _to_common_issue(issue: Dict[str, Any], source: str) -> Dict[str, Any]:
    """
    Convert different shapes to a common issue schema:
    {
      type, severity, description, field(optional), source, suggestion(optional), sources(optional)
    }
    """
    return {
        "type": issue.get("type") or issue.get("code") or "UNKNOWN",
        "severity": issue.get("severity") or "MEDIUM",
        "description": issue.get("description") or issue.get("message") or "",
        "field": issue.get("field"),
        "source": source,  # "RULE" or "LLM"
        "suggestion": issue.get("suggestion"),
        "sources": issue.get("sources")  # e.g., ["APPLICATION_FORM", "BANK_STATEMENT"]
    }


def _merge_two(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge two issues with the same key.
    Rules:
      - keep the higher severity
      - if one is RULE and the other is LLM, keep source="RULE+LLM"
      - keep non-empty suggestion/field/sources
    """
    sa = a.get("severity", "MEDIUM")
    sb = b.get("severity", "MEDIUM")

    # Choose higher severity
    if SEVERITY_RANK.get(sb, 2) > SEVERITY_RANK.get(sa, 2):
        winner, other = b, a
    else:
        winner, other = a, b

    merged = dict(winner)

    # Combine source marker
    src_a = _norm(a.get("source"))
    src_b = _norm(b.get("source"))
    if src_a != src_b:
        merged["source"] = "RULE+LLM"

    # Merge optional fields
    if not merged.get("field") and other.get("field"):
        merged["field"] = other["field"]

    if not merged.get("suggestion") and other.get("suggestion"):
        merged["suggestion"] = other["suggestion"]

    # Merge doc sources (list)
    s1 = merged.get("sources") or []
    s2 = other.get("sources") or []
    if isinstance(s1, list) and isinstance(s2, list):
        merged["sources"] = sorted(list(set(s1 + s2))) if (s1 or s2) else None

    return merged


def _summary(issues: List[Dict[str, Any]]) -> Dict[str, Any]:
    high = sum(1 for i in issues if i.get("severity") == "HIGH")
    med = sum(1 for i in issues if i.get("severity") == "MEDIUM")
    low = sum(1 for i in issues if i.get("severity") == "LOW")
    total = len(issues)

    decision_hint = "PASS"
    if high > 0:
        decision_hint = "NEEDS_REVIEW"

    return {
        "high": high,
        "medium": med,
        "low": low,
        "total": total,
        "decision_hint": decision_hint
    }


def merge_validations(
    rule_validation: Dict[str, Any],
    llm_validation: Dict[str, Any],
    llm_is_advisory: bool = True
) -> Dict[str, Any]:
    """
    Combines rule-based and LLM-based validations safely.

    Expected inputs:
      rule_validation: {"issues": [...], "validation_summary": {...}}
      llm_validation:  {"validation_flags": [...], "followup_questions": [...], "validation_summary": {...}}

    Output:
      {
        "issues": [...],                    # merged common issue format
        "followup_questions": [...],        # merged unique questions
        "validation_summary": {...},        # recomputed
        "sources": {"rule": ..., "llm": ...}# optional raw pointers
      }

    Safety:
      - If llm_is_advisory=True, LLM cannot downgrade/override rule HIGH decisions.
      - We still include LLM issues; we just trust rule outcomes for severity floor.
    """

    rule_issues_raw = rule_validation.get("issues", []) or []
    llm_flags_raw = llm_validation.get("validation_flags", []) or llm_validation.get("issues", []) or []

    # Convert to common format
    rule_issues = [_to_common_issue(i, "RULE") for i in rule_issues_raw]
    llm_issues = [_to_common_issue(i, "LLM") for i in llm_flags_raw]

    # Index by stable key and merge
    merged_by_key: Dict[str, Dict[str, Any]] = {}

    for issue in rule_issues + llm_issues:
        key = _issue_key(issue)
        if key in merged_by_key:
            merged_by_key[key] = _merge_two(merged_by_key[key], issue)
        else:
            merged_by_key[key] = issue

    merged_issues = list(merged_by_key.values())

    # Advisory mode safety: never allow merged result to reduce rule-based HIGH presence
    if llm_is_advisory:
        rule_high_exists = any(i.get("severity") == "HIGH" for i in rule_issues)
        if rule_high_exists:
            # Ensure summary indicates NEEDS_REVIEW even if LLM suggests otherwise
            pass  # summary is computed from merged_issues; rule HIGH will be present anyway

    # Merge follow-up questions (LLM only usually)
    followups = llm_validation.get("followup_questions", []) or []
    # de-dup questions by normalized text
    seen = set()
    merged_followups = []
    for q in followups:
        nq = _norm(q)
        if nq and nq not in seen:
            seen.add(nq)
            merged_followups.append(q)

    return {
        "issues": merged_issues,
        "followup_questions": merged_followups,
        "validation_summary": _summary(merged_issues),
        # optional raw for audit/debug
        "sources": {
            "rule": rule_validation,
            "llm": llm_validation
        }
    }
