import json
import base64
from typing import Dict, Any

from llm.llmlangfuse import chat_text, DEPLOYMENT_NAME
from llm.schemas import DOCUMENT_SCHEMAS
from llm.prompts import EXTRACTION_PROMPT
from jsonsanitizer import parse_json_loose


def _null_object_for_schema(schema: dict, note: str):
    out = {k: None for k in schema.keys()}
    out["_extraction_notes"] = note
    return out


def extraction_agent(doc_payload: Dict[str, Any]) -> dict:
    """
    doc_payload is one item from ingestion output:
      - text: {doc_type, content_type="text", document_text, ...}
      - image: {doc_type, content_type="image", image_base64, mime_type, ...}
    """
    assert DEPLOYMENT_NAME, "AZURE_OPENAI_DEPLOYMENT missing"

    doc_type = doc_payload["doc_type"]
    schema = DOCUMENT_SCHEMAS[doc_type]

    prompt = EXTRACTION_PROMPT.format(
        doc_type=doc_type,
        schema=json.dumps(schema, indent=2),
        document_text=(doc_payload.get("document_text") or "")[:120_000],
    )

    # For observability (Langfuse)
    application_id = doc_payload.get("application_id") or doc_payload.get("app_id") or None
    filename = doc_payload.get("filename") or doc_payload.get("file_name") or "unknown"
    content_type = doc_payload.get("content_type") or "unknown"

    if content_type == "image":
        b64 = doc_payload.get("image_base64")
        mime = doc_payload.get("mime_type") or "image/png"

        if not b64 or len(b64) < 200:
            return _null_object_for_schema(schema, "Missing/invalid image_base64 in ingestion payload")

        # Validate base64 early
        try:
            base64.b64decode(b64, validate=True)
        except Exception:
            return _null_object_for_schema(schema, "Invalid base64 data for image")

        data_url = f"data:{mime};base64,{b64}"

        messages = [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        }]

        raw = chat_text(
            messages=messages,
            temperature=0.0,
            trace_id=application_id,              # ✅ one trace per application
            # trace_name="gov-workflow",
            span_name="ExtractionAgent",          # ✅ one span per agent
            # tags=["extraction"],
            metadata={"doc_type": doc_type, "filename": filename, "content_type": content_type},
        )

    else:
        messages = [{"role": "user", "content": prompt}]

        raw = chat_text(
            messages=messages,
            temperature=0.0,
            trace_id=application_id,
            # trace_name="gov-workflow",
            span_name="ExtractionAgent",
            # tags=["extraction"],
            metadata={"doc_type": doc_type, "filename": filename, "content_type": content_type},
        )

    try:
        return parse_json_loose(raw)
    except Exception:
        return {"_extraction_notes": "LLM returned invalid JSON", "raw_output": raw}

# without langfuse
# import json
# import base64
# from typing import Dict, Any

# from llm.llmclient import client, DEPLOYMENT_NAME
# from llm.schemas import DOCUMENT_SCHEMAS
# from llm.prompts import EXTRACTION_PROMPT
# from jsonsanitizer import parse_json_loose


# def _null_object_for_schema(schema: dict, note: str):
#     out = {k: None for k in schema.keys()}
#     out["_extraction_notes"] = note
#     return out

# def extraction_agent(doc_payload: Dict[str, Any]) -> dict:
#     """
#     doc_payload is one item from ingestion output:
#       - text: {doc_type, content_type="text", document_text, ...}
#       - image: {doc_type, content_type="image", image_base64, mime_type, ...}
#     """
#     assert DEPLOYMENT_NAME, "AZURE_OPENAI_DEPLOYMENT missing"

#     doc_type = doc_payload["doc_type"]
#     schema = DOCUMENT_SCHEMAS[doc_type]

#     prompt = EXTRACTION_PROMPT.format(
#         doc_type=doc_type,
#         schema=json.dumps(schema, indent=2),
#         document_text=(doc_payload.get("document_text") or "")[:120_000],
#     )

#     # Image path (Vision)
#     if doc_payload.get("content_type") == "image":
#         b64 = doc_payload.get("image_base64")
#         mime = doc_payload.get("mime_type") or "image/png"

#         if not b64 or len(b64) < 200:
#             return _null_object_for_schema(schema, "Missing/invalid image_base64 in ingestion payload")

#         # Validate base64 early (catches common pipeline bugs)
#         try:
#             base64.b64decode(b64, validate=True)
#         except Exception:
#             return _null_object_for_schema(schema, "Invalid base64 data for image")

#         data_url = f"data:{mime};base64,{b64}"

#         resp = client.chat.completions.create(
#             model=DEPLOYMENT_NAME,
#             messages=[{
#                 "role": "user",
#                 "content": [
#                     {"type": "text", "text": prompt},
#                     {"type": "image_url", "image_url": {"url": data_url}},
#                 ],
#             }],
#             temperature=0,
#         )
#     else:
#         # Text path
#         resp = client.chat.completions.create(
#             model=DEPLOYMENT_NAME,
#             messages=[{"role": "user", "content": prompt}],
#             temperature=0,
#         )

#     raw = resp.choices[0].message.content

#     try:
#         return parse_json_loose(raw)
#     except Exception:
#         return {"_extraction_notes": "LLM returned invalid JSON", "raw_output": raw}