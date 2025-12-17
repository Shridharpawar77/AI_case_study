# # # from typing import Dict, Any

# # # def ingestion_agent(uploaded_docs: Dict[str, Any]) -> Dict[str, Any]:
# # #     """
# # #     uploaded_docs: {doc_type: {"filename": str, "text": str}}
# # #     """
# # #     # In PoC we assume UI already tells doc_type; this agent just standardizes.
# # #     normalized = {}
# # #     for doc_type, payload in uploaded_docs.items():
# # #         normalized[doc_type] = {
# # #             "doc_type": doc_type,
# # #             "filename": payload.get("filename"),
# # #             "document_text": payload.get("text", "") or ""
# # #         }
# # #     return normalized

# # from typing import Dict, Any
# # import base64

# # def ingestion_agent(uploaded_docs: Dict[str, Any]) -> Dict[str, Any]:
# #     """
# #     uploaded_docs format (from Streamlit):
# #     {
# #       doc_type: {
# #         "filename": str,
# #         "text": Optional[str],
# #         "file_bytes": Optional[bytes]
# #       }
# #     }
# #     """

# #     normalized = {}

# #     for doc_type, payload in uploaded_docs.items():
# #         filename = payload.get("filename", "").lower()

# #         # IMAGE documents (Emirates ID PNG/JPG)
# #         if filename.endswith((".png", ".jpg", ".jpeg")):
# #             image_bytes = payload.get("file_bytes")
# #             image_b64 = base64.b64encode(image_bytes).decode("utf-8") if image_bytes else None

# #             normalized[doc_type] = {
# #                 "doc_type": doc_type,
# #                 "content_type": "image",
# #                 "filename": payload.get("filename"),
# #                 "image_base64": image_b64
# #             }

# #         # TEXT documents (PDF/TXT)
# #         else:
# #             normalized[doc_type] = {
# #                 "doc_type": doc_type,
# #                 "content_type": "text",
# #                 "filename": payload.get("filename"),
# #                 "document_text": payload.get("text", "") or ""
# #             }

# #     return normalized

# from typing import Dict, Any
# import base64

# def ingestion_agent(uploaded_docs: Dict[str, Any]) -> Dict[str, Any]:
#     normalized = {}

#     for doc_type, payload in uploaded_docs.items():
#         filename = (payload.get("filename") or "").lower()
#         file_bytes = payload.get("file_bytes")

#         if filename.endswith((".png", ".jpg", ".jpeg")):
#             if not file_bytes:
#                 normalized[doc_type] = {
#                     "doc_type": doc_type,
#                     "content_type": "image",
#                     "filename": payload.get("filename"),
#                     "mime_type": None,
#                     "image_base64": None,
#                 }
#                 continue

#             mime = "image/png" if filename.endswith(".png") else "image/jpeg"
#             b64 = base64.b64encode(file_bytes).decode("utf-8")  # ✅ clean b64 (no b'')

#             normalized[doc_type] = {
#                 "doc_type": doc_type,
#                 "content_type": "image",
#                 "filename": payload.get("filename"),
#                 "mime_type": mime,
#                 "image_base64": b64,
#             }
#         else:
#             normalized[doc_type] = {
#                 "doc_type": doc_type,
#                 "content_type": "text",
#                 "filename": payload.get("filename"),
#                 "document_text": payload.get("text", "") or "",
#             }

#     return normalized

from typing import Dict, Any
import base64

def ingestion_agent(uploaded_docs: Dict[str, Any]) -> Dict[str, Any]:
    """
    uploaded_docs from Streamlit:
    {
      doc_type: {
        "filename": str,
        "text": Optional[str],        # for PDF/TXT
        "file_bytes": Optional[bytes] # for images (and also ok for pdf/txt)
      }
    }
    """
    normalized = {}

    for doc_type, payload in uploaded_docs.items():
        filename = (payload.get("filename") or "")
        filename_l = filename.lower()
        file_bytes = payload.get("file_bytes")

        # image docs (png/jpg/jpeg)
        if filename_l.endswith((".png", ".jpg", ".jpeg")):
            mime = "image/png" if filename_l.endswith(".png") else "image/jpeg"
            b64 = base64.b64encode(file_bytes).decode("utf-8") if file_bytes else None

            normalized[doc_type] = {
                "doc_type": doc_type,
                "content_type": "image",
                "filename": filename,
                "mime_type": mime,
                "image_base64": b64,
            }
        else:
            normalized[doc_type] = {
                "doc_type": doc_type,
                "content_type": "text",
                "filename": filename,
                "document_text": payload.get("text", "") or "",
            }

    return normalized

