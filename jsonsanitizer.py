import json
import re
from typing import Any, Dict

CODE_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)

def parse_json_loose(raw: str) -> Dict[str, Any]:
    """
    Handles:
    - ```json { ... } ``` fenced output
    - Extra text around JSON
    - Ensures we return a dict or raise ValueError
    """
    if not raw:
        raise ValueError("Empty response")

    text = raw.strip()

    # 1) If it's in a code fence, extract inside
    m = CODE_FENCE_RE.search(text)
    if m:
        text = m.group(1).strip()

    # 2) Try direct JSON parse
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass

    # 3) Fallback: find first {...} block
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = text[start:end+1].strip()
        obj = json.loads(candidate)
        if isinstance(obj, dict):
            return obj

    raise ValueError("Could not parse JSON")
