import base64
from typing import Any, Dict, Optional, Union

from llm.llmclient import client, MODEL_NAME
from llm.schemas import DOCUMENT_SCHEMAS
from llm.prompts import EXTRACTION_PROMPT
from jsonsanitizer import parse_json_loose


def _null_object_for_schema(schema: dict, note: str) -> dict:
    out = {k: None for k in schema.keys()}
    out["_extraction_notes"] = note
    return out


def _get_schema_for_doc(doc_payload: Dict[str, Any]) -> Optional[dict]:
    doc_type = (doc_payload.get("doc_type") or doc_payload.get("document_type") or "").strip()
    if not doc_type:
        return None
    return DOCUMENT_SCHEMAS.get(doc_type)


def _build_prompt(doc_payload: Dict[str, Any], schema: Optional[dict]) -> str:
    doc_type = (doc_payload.get("doc_type") or doc_payload.get("document_type") or "unknown").strip()
    text = (doc_payload.get("text") or doc_payload.get("content") or "").strip()

    # Best-effort formatting: support both .format(...) prompts and plain prompts.
    schema_str = ""
    if schema is not None:
        try:
            import json
            schema_str = json.dumps(schema, ensure_ascii=False)
        except Exception:
            schema_str = str(schema)

    try:
        # Common placeholder patterns we support: {doc_type}, {schema}, {schema_json}, {text}
        prompt = EXTRACTION_PROMPT.format(
            doc_type=doc_type,
            schema=schema_str,
            schema_json=schema_str,
            text=text,
        )
    except Exception:
        prompt = (
            f"{EXTRACTION_PROMPT}\n\n"
            f"Document type: {doc_type}\n"
            f"Return ONLY valid JSON matching this schema (keys exactly):\n{schema_str}\n\n"
            f"Text (if available):\n{text}"
        )

    return prompt


def _decode_image_bytes(b64_or_bytes: Union[str, bytes]) -> bytes:
    if isinstance(b64_or_bytes, bytes):
        return b64_or_bytes

    # Allow data URI prefix
    s = b64_or_bytes.strip()
    if s.startswith("data:"):
        s = s.split(",", 1)[-1]
    return base64.b64decode(s)


def extraction_agent(doc_payload: Dict[str, Any]) -> dict:
    """
    Extract structured fields from either:
      - text (doc_payload['text'])
      - image (doc_payload['image_b64'] or doc_payload['image_bytes'] or doc_payload['image_path'])

    Uses Ollama + minicpm-v through llmclient.py (client.chat_text).
    """
    if not MODEL_NAME:
        return {"_extraction_notes": "Configuration error: OLLAMA_MODEL is missing."}

    schema = _get_schema_for_doc(doc_payload)
    if schema is None:
        return _null_object_for_schema(
            {"doc_type": None},
            "Unknown or missing doc_type; cannot select schema."
        )

    prompt = _build_prompt(doc_payload, schema)

    # --------- Determine modality (vision vs text) ----------
    image_bytes: Optional[bytes] = None

    # Preferred: base64 image
    if doc_payload.get("image_b64"):
        try:
            image_bytes = _decode_image_bytes(doc_payload["image_b64"])
        except Exception:
            image_bytes = None

    # Alternative: raw bytes passed through pipeline
    if image_bytes is None and doc_payload.get("image_bytes"):
        try:
            image_bytes = _decode_image_bytes(doc_payload["image_bytes"])
        except Exception:
            image_bytes = None

    # Alternative: image file path
    image_path = doc_payload.get("image_path")
    if image_bytes is None and isinstance(image_path, str) and image_path.strip():
        # llmclient accepts a path directly too, but we normalize to bytes for safety
        try:
            with open(image_path, "rb") as f:
                image_bytes = f.read()
        except Exception:
            image_bytes = None

    # If no image, use text path (still ok for minicpm-v)
    messages = [{"role": "user", "content": prompt}]

    try:
        if image_bytes:
            raw = client.chat_text(messages=messages, images=[image_bytes], temperature=0.0)
        else:
            raw = client.chat_text(messages=messages, temperature=0.0)
    except Exception as e:
        return _null_object_for_schema(schema, f"Ollama call failed: {e}")

    try:
        return parse_json_loose(raw)
    except Exception:
        return {"_extraction_notes": "LLM returned invalid JSON", "raw_output": raw}
