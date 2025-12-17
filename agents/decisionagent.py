# import json
# from openai import OpenAI
# from prompts import DECISION_PROMPT

# from llmclient import client, DEPLOYMENT_NAME

# def decision_agent(extracted_docs: dict, validation: dict, model: str = "gpt-4o") -> dict:
#     # Try to pick application_id from extracted form if present
#     app_id = (extracted_docs.get("APPLICATION_FORM", {}) or {}).get("application_id")

#     prompt = DECISION_PROMPT.format(
#         extracted_data=json.dumps(extracted_docs, ensure_ascii=False),
#         validation_issues=json.dumps(validation.get("issues", []), ensure_ascii=False)
#     )

#     resp  = client.chat.completions.create(
#         model=DEPLOYMENT_NAME,   # Azure deployment
#         messages=[{"role": "user", "content": prompt}],
#         temperature=0
#     )

#     raw = resp.choices[0].message.content
#     try:
#         out = json.loads(raw)
#         if "application_id" not in out:
#             out["application_id"] = app_id
#         return out
#     except json.JSONDecodeError:
#         return {"application_id": app_id, "decision": "NEEDS_REVIEW", "confidence": 0.1,
#                 "reasons": ["Decision model returned invalid JSON"], "next_steps": ["Retry decision generation"]}
import json
from typing import Dict, Any

from llmclient import client, DEPLOYMENT_NAME
from prompts import DECISION_PROMPT

def decision_agent(extracted_docs: Dict[str, Any], validation: Dict[str, Any], eligibility_signal: Dict[str, Any]) -> Dict[str, Any]:
    assert DEPLOYMENT_NAME, "AZURE_OPENAI_DEPLOYMENT missing"

    app_id = (extracted_docs.get("APPLICATION_FORM", {}) or {}).get("application_id")

    prompt = DECISION_PROMPT.format(
        extracted_data=json.dumps(extracted_docs, ensure_ascii=False),
        validation_issues=json.dumps(validation.get("issues", []), ensure_ascii=False),
        eligibility_signal=json.dumps(eligibility_signal, ensure_ascii=False),
    )

    resp = client.chat.completions.create(
        model=DEPLOYMENT_NAME,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )

    raw = resp.choices[0].message.content
    try:
        #out = json.loads(raw)
        from jsonsanitizer import parse_json_loose
        out = parse_json_loose(raw)
        if "application_id" not in out or out["application_id"] in (None, "", "null"):
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
            "debug": {"validation_summary": validation.get("validation_summary", {})}
        }
