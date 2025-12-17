import json
from typing import Any, Dict

from llm.llmclient import client, MODEL_NAME
from llm.prompts import DECISION_PROMPT


def decision_agent(
    extracted_docs: Dict[str, Any],
    validation: Dict[str, Any],
    eligibility_signal: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Generates final underwriting decision JSON using local Ollama model (minicpm-v).
    Expected output schema (example):
      {
        "application_id": "...",
        "decision": "APPROVED"|"REJECTED"|"NEEDS_REVIEW",
        "confidence": 0.0-1.0,
        "reasons": [...],
        "next_steps": [...],
        "debug": {...}
      }
    """

    if not MODEL_NAME:
        return {
            "application_id": (extracted_docs.get("APPLICATION_FORM", {}) or {}).get("application_id"),
            "decision": "NEEDS_REVIEW",
            "confidence": 0.1,
            "reasons": ["Configuration error: OLLAMA_MODEL is missing"],
            "next_steps": ["Set OLLAMA_MODEL in environment/.env"],
            "debug": {"validation_summary": validation.get("validation_summary", {})},
        }

    app_id = (extracted_docs.get("APPLICATION_FORM", {}) or {}).get("application_id")

    prompt = DECISION_PROMPT.format(
        extracted_data=json.dumps(extracted_docs, ensure_ascii=False),
        validation_issues=json.dumps(validation.get("issues", []), ensure_ascii=False),
        eligibility_signal=json.dumps(eligibility_signal, ensure_ascii=False),
    )

    messages = [
        {"role": "system", "content": "You are a strict JSON generator. Return ONLY valid JSON."},
        {"role": "user", "content": prompt},
    ]

    # Ollama chat (non-stream)
    answer = client.chat_text(messages=messages, temperature=0.0)

    try:
        out = json.loads(answer)

        # Ensure application_id is present
        if app_id and not out.get("application_id"):
            out["application_id"] = app_id

        # Attach validation summary into debug if not present
        out.setdefault("debug", {})
        out["debug"].setdefault("validation_summary", validation.get("validation_summary", {}))

        return out
    except json.JSONDecodeError:
        return {
            "application_id": app_id,
            "decision": "NEEDS_REVIEW",
            "confidence": 0.1,
            "reasons": ["Decision model returned invalid JSON"],
            "next_steps": ["Retry decision generation or check prompt/schema"],
            "debug": {"validation_summary": validation.get("validation_summary", {})},
        }
