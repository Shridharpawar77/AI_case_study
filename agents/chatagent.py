import json
import re
from typing import Any, Dict, List, Optional
from llm.prompts import CHAT_PROMPT
from llm.llmlangfuse import chat_text, DEPLOYMENT_NAME

from llm.llmclient import client, DEPLOYMENT_NAME

# ----------------------------
# Helpers
# ----------------------------

SEVERITY_RANK = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}

GREETINGS = {
    "hi", "hello", "hey", "hii", "hiii", "hola", "namaste", "good morning", "good afternoon", "good evening"
}

THANKS = {"thanks", "thank you", "thx", "ty", "appreciate it"}

BYE = {"bye", "goodbye", "see you", "take care", "cya"}

def _is_smalltalk(question: str) -> str | None:
    """
    Returns intent: 'greet' | 'thanks' | 'bye' | None
    """
    q = (question or "").strip().lower()

    # very short greetings like "hi", "hello"
    if q in GREETINGS:
        return "greet"

    if q in THANKS:
        return "thanks"

    if q in BYE:
        return "bye"

    # patterns (e.g., "hi there", "hello!")
    q2 = re.sub(r"[^\w\s]", "", q)
    if any(q2.startswith(g) for g in ["hi ", "hello ", "hey ", "good morning", "good afternoon", "good evening", "namaste"]):
        return "greet"

    if "thank" in q2 or q2.startswith("thanks"):
        return "thanks"

    if q2.startswith("bye") or "goodbye" in q2:
        return "bye"

    return None


def _smalltalk_reply(intent: str, context_loaded: bool) -> str:
    if intent == "greet":
        if context_loaded:
            return "Hi! 👋 Ask me anything about this application—e.g., “Why this decision?”, “What validation checks were done?”, or “What documents are missing?”"
        return "Hi! 👋 Upload documents and run the workflow, then ask me questions about the application."
    if intent == "thanks":
        return "You’re welcome! Want a summary, validation explanation, or next steps?"
    if intent == "bye":
        return "Bye 👋 If you need anything else on the application workflow, just message."
    return "Hi!"



def _norm(s: Any) -> str:
    if s is None:
        return ""
    return str(s).strip().lower()


def _clean_whitespace(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s


def _safe_json_dumps(obj: Any, max_chars: int = 120_000) -> str:
    """
    Safely serialize context for prompt; truncate to avoid huge prompts.
    """
    try:
        text = json.dumps(obj, ensure_ascii=False, indent=2)
    except Exception:
        text = str(obj)

    if len(text) > max_chars:
        text = text[:max_chars] + "\n...<truncated>..."
    return text


def _format_issue(issue: Dict[str, Any]) -> str:
    t = issue.get("type") or issue.get("code") or "ISSUE"
    sev = issue.get("severity") or "MEDIUM"
    desc = issue.get("description") or issue.get("message") or ""
    field = issue.get("field")
    srcs = issue.get("sources")
    extra = []
    if field:
        extra.append(f"field={field}")
    if srcs:
        extra.append(f"sources={srcs}")
    extra_txt = f" ({', '.join(extra)})" if extra else ""
    return f"[{sev}] {t}: {desc}{extra_txt}"


def _list_present_missing_docs(extracted_docs: Dict[str, Any]) -> Dict[str, List[str]]:
    all_docs = ["APPLICATION_FORM", "EMIRATES_ID", "BANK_STATEMENT", "CREDIT_REPORT", "ASSETS_LIABILITIES", "RESUME"]
    present = [d for d in all_docs if extracted_docs.get(d)]
    missing = [d for d in all_docs if d not in present]
    return {"present": present, "missing": missing}


# ----------------------------
# Deterministic quick answers
# ----------------------------

def _quick_answer(context: Dict[str, Any], question: str, mode: str = "short") -> Optional[str]:
    """
    Returns a deterministic response for common questions.
    If returns None, caller should use LLM fallback.
    """
    q = _norm(question)

    extracted = context.get("extracted_docs", {}) or {}
    validation = context.get("validation", {}) or {}
    eligibility = context.get("eligibility_signal", {}) or {}
    decision = context.get("decision", {}) or {}

    issues = validation.get("issues", []) or []
    summary = validation.get("validation_summary", {}) or {}

    # Summary / overview
    if any(k in q for k in ["summarize", "summary", "overview", "tl;dr", "tldr"]):
        app = extracted.get("APPLICATION_FORM", {}) or {}
        name = app.get("applicant_name")
        app_id = app.get("application_id")
        income = app.get("declared_monthly_income")
        fam = app.get("family_size")
        emp = app.get("employment_status")
        dec = decision.get("decision")
        conf = decision.get("confidence")

        lines = [
            f"Application {app_id or '(unknown id)'} for {name or '(unknown applicant)'}.",
            f"Declared income: {income}, family size: {fam}, employment: {emp}.",
            f"Validation: {summary.get('total', 0)} issue(s). Eligibility: {eligibility.get('eligibility_status')}.",
            f"Decision: {dec} (confidence {conf}).",
        ]
        return "\n".join(lines) if mode != "short" else "\n".join(lines[:2] + [lines[-1]])

    # Why decision?
    if ("why" in q or "reason" in q) and any(k in q for k in ["decision", "approve", "decline", "needs review", "soft"]):
        dec = decision.get("decision")
        conf = decision.get("confidence")
        reasons = decision.get("reasons") or []
        next_steps = decision.get("next_steps") or []
        out = [
            f"Decision: {dec} (confidence {conf}).",
            "Reasons:",
            *[f"- {r}" for r in reasons[:8]],
        ]
        if mode in ("detailed", "audit") and next_steps:
            out += ["Next steps:", *[f"- {s}" for s in next_steps[:8]]]
        return "\n".join(out)

    # Validation checks / issues
    if any(k in q for k in ["validation", "checks performed", "checks", "issues", "flags"]):
        if not issues:
            return "No validation issues were detected in this run."
        formatted = "\n".join([f"- {_format_issue(i)}" for i in issues[:12]])
        return f"Validation issues ({len(issues)}):\n{formatted}"

    # Missing documents
    if any(k in q for k in ["missing document", "missing docs", "missing documents", "what documents", "which documents", "upload"]):
        pm = _list_present_missing_docs(extracted)
        return f"Uploaded: {pm['present']}\nMissing: {pm['missing']}"

    # Enablement recommendations
    if any(k in q for k in ["enablement", "upskill", "upskilling", "job matching", "counsel", "counseling", "training"]):
        recs = decision.get("enablement_recommendations") or []
        if not recs:
            return "No enablement recommendations are present in the decision output."
        lines = []
        for r in recs[:6]:
            cat = r.get("category")
            rec = r.get("recommendation")
            reason = r.get("reason")
            if mode == "short":
                lines.append(f"- {cat}: {rec}")
            else:
                lines.append(f"- {cat}: {rec} (reason: {reason})")
        return "Enablement recommendations:\n" + "\n".join(lines)

    # Eligibility status
    if any(k in q for k in ["eligibility", "eligible", "ineligible", "borderline"]):
        return f"Eligibility signal: {eligibility}"

    return None


# ----------------------------
# LLM prompt (grounded)
# ----------------------------


def chat_agent(
    context: Dict[str, Any],
    question: str,
    chat_history: Optional[List[Dict[str, str]]] = None,
    mode: str = "short",
) -> str:
    """
    context expected keys:
      - extracted_docs
      - validation
      - eligibility_signal
      - decision

    chat_history: [{"role": "user"|"assistant", "content": "..."}]
    mode: "short" | "detailed" | "audit"
    """

    if not DEPLOYMENT_NAME:
        return "Configuration error: AZURE_OPENAI_DEPLOYMENT is missing."

    question = _clean_whitespace(question)
    if not question:
        return "Please type a question."
    
    # Small-talk / greeting layer (prevents dumping case info on "Hi")
    intent = _is_smalltalk(question)
    if intent:
        context_loaded = bool((context or {}).get("extracted_docs")) and bool((context or {}).get("decision"))
        return _smalltalk_reply(intent, context_loaded)

    decision_val = (context.get("decision") or {}).get("decision")
    q_low = _norm(question)

    # 1) Decision mismatch correction (fast path)
    if decision_val and ("needs_review" in q_low or "needs review" in q_low) and decision_val != "NEEDS_REVIEW":
        return (
            f"This application is not marked NEEDS_REVIEW. "
            f"The current decision is {decision_val}. "
            f"Ask: 'Why is this {decision_val}?' or rerun the workflow for another case."
        )

    # 2) Deterministic quick answers (fast + reliable)
    quick = _quick_answer(context, question, mode=mode)
    if quick:
        return quick

    # 3) LLM fallback (grounded + history-aware)
    context_json = _safe_json_dumps(context)

    prompt = CHAT_PROMPT.format(
        context_json=context_json,
        mode=mode,
        question=question,
    )

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": "You are a helpful, accurate assistant."}
    ]

    # Keep last N turns for memory
    if chat_history:
        for m in chat_history[-6:]:
            role = m.get("role")
            content = m.get("content")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": prompt})

    # Optional: be cautious if confidence is low
    conf = (context.get("decision") or {}).get("confidence")
    temperature = 0.2
    if isinstance(conf, (int, float)) and conf < 0.5:
        temperature = 0.0  # reduce creativity

    # resp = client.chat.completions.create(
    #     model=DEPLOYMENT_NAME,
    #     messages=messages,
    #     temperature=temperature,
    # )
    # return (resp.choices[0].message.content or "").strip()
    answer = chat_text(
        messages=messages,
        temperature=0.2,
        trace_id=application_id,
        span_name="ChatAgent",
        metadata={"stage": "chat"},
    )
    return {"answer": answer}
    
