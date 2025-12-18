import os
import time
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from openai import AzureOpenAI

load_dotenv()

client = AzureOpenAI(
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    azure_endpoint=os.getenv("AZURE_OPENAI_API_BASE"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
)
DEPLOYMENT_NAME = os.getenv("AZURE_OPENAI_DEPLOYMENT")

LANGFUSE_ENABLED = os.getenv("LANGFUSE_ENABLED", "false").lower() in ("1", "true", "yes")

_lf = None


def _get_langfuse():
    global _lf
    if not LANGFUSE_ENABLED:
        return None
    if _lf is not None:
        return _lf
    try:
        from langfuse import get_client

        _lf = get_client()  # reads LANGFUSE_PUBLIC_KEY/SECRET_KEY/LANGFUSE_BASE_URL (or host)
        return _lf
    except Exception:
        return None


def _safe_messages(messages: List[Dict[str, Any]], max_chars: int = 1200) -> List[Dict[str, Any]]:
    """Truncate and redact vision/base64 payloads."""
    safe = []
    for m in messages or []:
        role = m.get("role")
        content = m.get("content", "")

        if isinstance(content, list):
            parts = []
            for part in content:
                if not isinstance(part, dict):
                    continue
                ptype = part.get("type")
                if ptype == "text":
                    text = str(part.get("text", ""))
                    if len(text) > max_chars:
                        text = text[:max_chars] + "…"
                    parts.append({"type": "text", "text": text})
                elif ptype == "image_url":
                    parts.append({"type": "image_url", "image_url": {"url": "<redacted>"}})
                else:
                    parts.append({"type": str(ptype or "unknown")})
            safe.append({"role": role, "content": parts})
        else:
            text = "" if content is None else str(content)
            if len(text) > max_chars:
                text = text[:max_chars] + "…"
            safe.append({"role": role, "content": text})
    return safe

def chat_text(
    messages,
    temperature: float = 0.0,
    max_tokens=None,
    trace_id: str | None = None,     # your business id e.g. APP-123
    span_name: str = "LLMCall",
    metadata: dict | None = None,
):
    assert DEPLOYMENT_NAME, "AZURE_OPENAI_DEPLOYMENT missing"
    lf = _get_langfuse()
    start = time.time()

    # No Langfuse → normal call
    if not lf:
        resp = client.chat.completions.create(
            model=DEPLOYMENT_NAME,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return (resp.choices[0].message.content or "").strip()

    # ---- Convert your external trace_id into a valid Langfuse trace id ----
    trace_context = None
    if trace_id:
        # deterministic 32-hex trace id derived from your external id
        lf_trace_id = lf.create_trace_id(seed=str(trace_id))
        trace_context = {"trace_id": lf_trace_id}

    safe_in = {
        "deployment": DEPLOYMENT_NAME,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": _safe_messages(messages),
        "metadata": metadata or {},
    }

    # ✅ Use trace_context (not trace_id)
    with lf.start_as_current_observation(
        as_type="generation",
        name=span_name,
        input=safe_in,
        metadata=metadata or {},
        trace_context=trace_context,   # <---- this is the key change
    ) as obs:
        resp = client.chat.completions.create(
            model=DEPLOYMENT_NAME,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        text = (resp.choices[0].message.content or "").strip()

        elapsed_ms = int((time.time() - start) * 1000)
        obs.update(
            output={"assistant_content": text[:2000]},
            metadata={"elapsed_ms": elapsed_ms, **(metadata or {})},
        )

    try:
        lf.flush()  # important for Streamlit reruns
    except Exception:
        pass

    return text
