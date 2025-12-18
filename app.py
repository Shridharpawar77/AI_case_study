import os
import streamlit as st
from dotenv import load_dotenv
from PyPDF2 import PdfReader

from graph import build_graph
from agents.chatagent import chat_agent  # <-- your improved file
from db.db import store_workflow_output


# ----------------------------
# Config
# ----------------------------

DOC_TYPES = [
    "APPLICATION_FORM",
    "EMIRATES_ID",
    "BANK_STATEMENT",
    "CREDIT_REPORT",
    "ASSETS_LIABILITIES",
    "RESUME",
]

ALLOWED_FILE_TYPES = ["pdf", "txt", "png", "jpg", "jpeg"]

# SUGGESTED_QUESTIONS = [
#     "Summarize this application in 5 lines.",
#     "Why is this decision given?",
#     "What validation checks were performed?",
#     "What documents are missing to increase confidence?",
#     "Explain enablement recommendations and why they were suggested.",
#     "What could change the decision to NEEDS_REVIEW?",
# ]


# ----------------------------
# Utilities
# ----------------------------

def init_session_state():
    if "messages" not in st.session_state:
        st.session_state["messages"] = []  # chat history: [{"role":..., "content":...}]
    if "last_result" not in st.session_state:
        st.session_state["last_result"] = None
    if "uploaded_docs" not in st.session_state:
        st.session_state["uploaded_docs"] = {}


def file_to_text(uploaded_file) -> str:
    """
    - PDF -> extract text via PyPDF2
    - TXT -> decode to string
    - Images -> return "" (handled by GPT-4o Vision via ingestion/extraction)
    """
    name = uploaded_file.name.lower()

    if name.endswith(".pdf"):
        try:
            reader = PdfReader(uploaded_file)
            pages = []
            for p in reader.pages[:15]:
                pages.append(p.extract_text() or "")
            return "\n".join(pages).strip()
        except Exception:
            return ""

    if name.endswith(".txt"):
        try:
            return uploaded_file.getvalue().decode("utf-8", errors="ignore").strip()
        except Exception:
            return ""

    return ""

def summarize_decision(result: dict) -> str:
    """
    Build a short 3–4 line summary using ONLY workflow outputs (no LLM).
    """
    decision = (result or {}).get("decision", {}) or {}
    validation = (result or {}).get("validation", {}) or {}
    eligibility = (result or {}).get("eligibility_signal", {}) or {}
    extracted = (result or {}).get("extracted_docs", {}) or {}

    app = extracted.get("APPLICATION_FORM", {}) or {}

    app_id = decision.get("application_id") or app.get("application_id") or "UNKNOWN"
    dec = decision.get("decision") or "UNKNOWN"
    conf = decision.get("confidence")
    elig = eligibility.get("eligibility_status", "UNKNOWN")

    vsum = validation.get("validation_summary", {}) or {}
    issues_total = vsum.get("total", 0)
    high = vsum.get("high", 0)
    med = vsum.get("medium", 0)
    low = vsum.get("low", 0)

    reasons = decision.get("reasons") or []
    reasons_line = reasons[0] if reasons else "No reasons provided."

    lines = [
        f"Application: {app_id} | Decision: {dec} (confidence: {conf})",
        f"Eligibility: {elig} | Validation issues: total={issues_total} (HIGH={high}, MED={med}, LOW={low})",
        f"Key reason: {reasons_line}",
    ]

    # Optional 4th line: next step
    next_steps = decision.get("next_steps") or []
    if next_steps:
        lines.append(f"Next step: {next_steps[0]}")

    return "\n".join(lines)


def build_uploaded_docs_from_sidebar() -> dict:
    uploaded_docs = {}

    st.sidebar.header("Upload documents")
    st.sidebar.caption("PDF/TXT for text docs, PNG/JPG for Emirates ID (Vision).")

    for dt in DOC_TYPES:
        f = st.sidebar.file_uploader(
            dt,
            type=ALLOWED_FILE_TYPES,
            key=f"uploader_{dt}",
            help="Images will be processed via GPT-4o Vision. PDFs/TXT via text extraction."
        )
        if f:
            filename = f.name
            file_bytes = f.getvalue()
            text = file_to_text(f)

            uploaded_docs[dt] = {
                "filename": filename,
                "text": text,
                "file_bytes": file_bytes,
            }

    return uploaded_docs


def validate_env_or_show_error() -> bool:
    missing = []
    if not os.getenv("AZURE_OPENAI_API_KEY"):
        missing.append("AZURE_OPENAI_API_KEY")
    if not os.getenv("AZURE_OPENAI_API_BASE"):
        missing.append("AZURE_OPENAI_API_BASE")
    if not os.getenv("AZURE_OPENAI_API_VERSION"):
        missing.append("AZURE_OPENAI_API_VERSION")
    if not os.getenv("AZURE_OPENAI_DEPLOYMENT"):
        missing.append("AZURE_OPENAI_DEPLOYMENT")

    if missing:
        st.error("Missing environment variables: " + ", ".join(missing))
        st.info("Check your .env file in project root.")
        return False
    return True


def run_workflow(uploaded_docs: dict) -> dict:
    app = build_graph()
    state_in = {"uploaded_docs": uploaded_docs}
    return app.invoke(state_in)


def render_uploaded_preview(uploaded_docs: dict):
    st.subheader("Uploaded documents (preview)")

    if not uploaded_docs:
        st.info("Upload at least APPLICATION_FORM + EMIRATES_ID to test quickly.")
        return

    for dt, payload in uploaded_docs.items():
        fn = payload.get("filename", "")
        with st.expander(f"{dt}: {fn}", expanded=False):
            if fn.lower().endswith((".png", ".jpg", ".jpeg")):
                st.image(payload["file_bytes"], caption=fn, use_container_width=True)
                st.caption("This image will be processed via GPT-4o Vision (no OCR).")
            else:
                preview = (payload.get("text") or "")[:4000]
                st.text(preview if preview else "(No text extracted from this file)")

def render_decision_summary(last_result: dict):
    if not last_result:
        return

    summary = last_result.get("decision_summary")
    if not summary:
        summary = summarize_decision(last_result)
        last_result["decision_summary"] = summary  # cache

    st.subheader("Decision Summary")
    st.code(summary, language="text")


def render_workflow_output(result: dict):
    st.subheader("Workflow output")

    if not result:
        st.info("Run the workflow to see outputs.")
        return

    st.markdown("### Extracted Data")
    st.json(result.get("extracted_docs", {}))

    st.markdown("### Validation")
    st.json(result.get("validation", {}))

    st.markdown("### Eligibility Signal")
    st.json(result.get("eligibility_signal", {}))

    st.markdown("### Final Decision")
    st.json(result.get("decision", {}))


def build_chat_context_from_last_result(last_result: dict) -> dict:
    """
    Build the unified context required by chatagent.py
    """
    extracted_docs = (last_result or {}).get("extracted_docs", {}) or {}
    decision_output = (last_result or {}).get("decision", {}) or {}
    validation_output = (last_result or {}).get("validation", {}) or {}
    eligibility_signal = (last_result or {}).get("eligibility_signal", {}) or {}

    return {
        "extracted_docs": extracted_docs,
        "validation": validation_output,
        "eligibility_signal": eligibility_signal,
        "decision": decision_output,
    }


def push_user_message(text: str):
    st.session_state["messages"].append({"role": "user", "content": text})


def push_assistant_message(text: str):
    st.session_state["messages"].append({"role": "assistant", "content": text})


# def render_suggested_questions():
#     st.markdown("### Suggested questions")
#     cols = st.columns(3)
#     for i, q in enumerate(SUGGESTED_QUESTIONS):
#         if cols[i % 3].button(q, key=f"sugg_{i}"):
#             push_user_message(q)
#             st.session_state["pending_user_msg"] = q  # 👈 queue it for backend processing
#             st.rerun()

def render_chat_ui():
    st.subheader("Interactive Chat")

    last = st.session_state.get("last_result")
    if not last:
        st.info("Run the workflow first, then chat here.")
        return

    # Chat controls
    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        mode = st.selectbox("Mode", ["short", "detailed", "audit"], index=1)
    with c2:
        if st.button("Clear chat"):
            st.session_state["messages"] = []
            st.rerun()
    with c3:
        st.caption("Tip: Use 'audit' mode to get doc-based explanations.")

    # render_suggested_questions()
    # process_pending_chat(mode)

    # Display history
    for m in st.session_state["messages"]:
        with st.chat_message(m["role"]):
            st.write(m["content"])

    # Input
    user_msg = st.chat_input("Ask about this application...")
    if not user_msg:
        return

    push_user_message(user_msg)

    context = build_chat_context_from_last_result(last)
    history = st.session_state.get("messages", [])

    try:
        answer = chat_agent(
            context=context,
            question=user_msg,
            chat_history=history,
            mode=mode,
        )
    except Exception as e:
        answer = f"Chat error: {e}"

    push_assistant_message(answer)
    st.rerun()

def process_pending_chat(mode: str):
    """
    If a suggested question (or any pending question) exists, run chat_agent and append response.
    """
    last = st.session_state.get("last_result")
    pending = st.session_state.get("pending_user_msg")

    if not last or not pending:
        return

    context = build_chat_context_from_last_result(last)
    history = st.session_state.get("messages", [])

    try:
        answer = chat_agent(
            context=context,
            question=pending,
            chat_history=history,
            mode=mode
        )
    except Exception as e:
        answer = f"Chat error: {e}"

    push_assistant_message(answer)

    # clear pending so it doesn't re-run forever
    # st.session_state["pending_user_msg"] = None

def save_to_db_or_warn(out: dict):
    try:
        from db import store_workflow_output
        app_id = store_workflow_output(out, model_name=os.getenv("AZURE_OPENAI_DEPLOYMENT"))
        st.success(f"Saved to DB for application_id={app_id}")
    except Exception as e:
        st.warning(f"Workflow completed but DB save failed: {e}")


# ----------------------------
# Main
# ----------------------------
def main():
    load_dotenv()
    init_session_state()

    st.set_page_config(page_title="Social Support PoC", layout="wide")
    st.title("Social Support Application — PoC (LangGraph + Azure OpenAI)")

    # Sidebar build uploads
    uploaded_docs = build_uploaded_docs_from_sidebar()
    st.session_state["uploaded_docs"] = uploaded_docs

    run_btn = st.sidebar.button("Run Workflow", type="primary")

    # Main layout
    col1, col2 = st.columns([1, 1])

    with col1:
        render_uploaded_preview(uploaded_docs)

    with col2:
        if run_btn:
            if validate_env_or_show_error() and uploaded_docs:
                try:
                    out = run_workflow(uploaded_docs)
                    out["decision_summary"] = summarize_decision(out)
                    st.session_state["last_result"] = out
                    save_to_db_or_warn(out)
                except Exception as e:
                    st.exception(e)

        render_workflow_output(st.session_state.get("last_result"))

    # ✅ show summary between workflow output and chat
    st.divider()
    render_decision_summary(st.session_state.get("last_result"))

    st.divider()
    render_chat_ui()


if __name__ == "__main__":
    main()

# import os
# import streamlit as st
# from dotenv import load_dotenv
# from PyPDF2 import PdfReader

# from graph import build_graph
# from agents.chatagent import chat_agent  # <-- your improved file
# from db import store_workflow_output
# import time
# import traceback
# from observability import get_langfuse

# # ----------------------------
# # Config
# # ----------------------------

# DOC_TYPES = [
#     "APPLICATION_FORM",
#     "EMIRATES_ID",
#     "BANK_STATEMENT",
#     "CREDIT_REPORT",
#     "ASSETS_LIABILITIES",
#     "RESUME",
# ]

# ALLOWED_FILE_TYPES = ["pdf", "txt", "png", "jpg", "jpeg"]

# SUGGESTED_QUESTIONS = [
#     "Summarize this application in 5 lines.",
#     "Why is this decision given?",
#     "What validation checks were performed?",
#     "What documents are missing to increase confidence?",
#     "Explain enablement recommendations and why they were suggested.",
#     "What could change the decision to NEEDS_REVIEW?",
# ]


# ----------------------------
# Utilities
# ----------------------------

# def init_session_state():
#     if "messages" not in st.session_state:
#         st.session_state["messages"] = []  # chat history: [{"role":..., "content":...}]
#     if "last_result" not in st.session_state:
#         st.session_state["last_result"] = None
#     if "uploaded_docs" not in st.session_state:
#         st.session_state["uploaded_docs"] = {}


# def file_to_text(uploaded_file) -> str:
#     """
#     - PDF -> extract text via PyPDF2
#     - TXT -> decode to string
#     - Images -> return "" (handled by GPT-4o Vision via ingestion/extraction)
#     """
#     name = uploaded_file.name.lower()

#     if name.endswith(".pdf"):
#         try:
#             reader = PdfReader(uploaded_file)
#             pages = []
#             for p in reader.pages[:15]:
#                 pages.append(p.extract_text() or "")
#             return "\n".join(pages).strip()
#         except Exception:
#             return ""

#     if name.endswith(".txt"):
#         try:
#             return uploaded_file.getvalue().decode("utf-8", errors="ignore").strip()
#         except Exception:
#             return ""

#     return ""

# def summarize_decision(result: dict) -> str:
#     """
#     Build a short 3–4 line summary using ONLY workflow outputs (no LLM).
#     """
#     decision = (result or {}).get("decision", {}) or {}
#     validation = (result or {}).get("validation", {}) or {}
#     eligibility = (result or {}).get("eligibility_signal", {}) or {}
#     extracted = (result or {}).get("extracted_docs", {}) or {}

#     app = extracted.get("APPLICATION_FORM", {}) or {}

#     app_id = decision.get("application_id") or app.get("application_id") or "UNKNOWN"
#     dec = decision.get("decision") or "UNKNOWN"
#     conf = decision.get("confidence")
#     elig = eligibility.get("eligibility_status", "UNKNOWN")

#     vsum = validation.get("validation_summary", {}) or {}
#     issues_total = vsum.get("total", 0)
#     high = vsum.get("high", 0)
#     med = vsum.get("medium", 0)
#     low = vsum.get("low", 0)

#     reasons = decision.get("reasons") or []
#     reasons_line = reasons[0] if reasons else "No reasons provided."

#     lines = [
#         f"Application: {app_id} | Decision: {dec} (confidence: {conf})",
#         f"Eligibility: {elig} | Validation issues: total={issues_total} (HIGH={high}, MED={med}, LOW={low})",
#         f"Key reason: {reasons_line}",
#     ]

#     # Optional 4th line: next step
#     next_steps = decision.get("next_steps") or []
#     if next_steps:
#         lines.append(f"Next step: {next_steps[0]}")

#     return "\n".join(lines)


# def build_uploaded_docs_from_sidebar() -> dict:
#     uploaded_docs = {}

#     st.sidebar.header("Upload documents")
#     st.sidebar.caption("PDF/TXT for text docs, PNG/JPG for Emirates ID (Vision).")

#     for dt in DOC_TYPES:
#         f = st.sidebar.file_uploader(
#             dt,
#             type=ALLOWED_FILE_TYPES,
#             key=f"uploader_{dt}",
#             help="Images will be processed via GPT-4o Vision. PDFs/TXT via text extraction."
#         )
#         if f:
#             filename = f.name
#             file_bytes = f.getvalue()
#             text = file_to_text(f)

#             uploaded_docs[dt] = {
#                 "filename": filename,
#                 "text": text,
#                 "file_bytes": file_bytes,
#             }

#     return uploaded_docs


# def validate_env_or_show_error() -> bool:
#     missing = []
#     if not os.getenv("AZURE_OPENAI_API_KEY"):
#         missing.append("AZURE_OPENAI_API_KEY")
#     if not os.getenv("AZURE_OPENAI_API_BASE"):
#         missing.append("AZURE_OPENAI_API_BASE")
#     if not os.getenv("AZURE_OPENAI_API_VERSION"):
#         missing.append("AZURE_OPENAI_API_VERSION")
#     if not os.getenv("AZURE_OPENAI_DEPLOYMENT"):
#         missing.append("AZURE_OPENAI_DEPLOYMENT")

#     if missing:
#         st.error("Missing environment variables: " + ", ".join(missing))
#         st.info("Check your .env file in project root.")
#         return False
#     return True


# def run_workflow(uploaded_docs: dict, trace_id: str | None = None) -> dict:
#     app = build_graph()
#     state_in = {"uploaded_docs": uploaded_docs}
#     if trace_id:
#         state_in["trace_id"] = trace_id
#     return app.invoke(state_in)



# def render_uploaded_preview(uploaded_docs: dict):
#     st.subheader("Uploaded documents (preview)")

#     if not uploaded_docs:
#         st.info("Upload at least APPLICATION_FORM + EMIRATES_ID to test quickly.")
#         return

#     for dt, payload in uploaded_docs.items():
#         fn = payload.get("filename", "")
#         with st.expander(f"{dt}: {fn}", expanded=False):
#             if fn.lower().endswith((".png", ".jpg", ".jpeg")):
#                 st.image(payload["file_bytes"], caption=fn, use_container_width=True)
#                 st.caption("This image will be processed via GPT-4o Vision (no OCR).")
#             else:
#                 preview = (payload.get("text") or "")[:4000]
#                 st.text(preview if preview else "(No text extracted from this file)")

# def render_decision_summary(last_result: dict):
#     if not last_result:
#         return

#     summary = last_result.get("decision_summary")
#     if not summary:
#         summary = summarize_decision(last_result)
#         last_result["decision_summary"] = summary  # cache

#     st.subheader("Decision Summary")
#     st.code(summary, language="text")


# def render_workflow_output(result: dict):
#     st.subheader("Workflow output")

#     if not result:
#         st.info("Run the workflow to see outputs.")
#         return

#     st.markdown("### Extracted Data")
#     st.json(result.get("extracted_docs", {}))

#     st.markdown("### Validation")
#     st.json(result.get("validation", {}))

#     st.markdown("### Eligibility Signal")
#     st.json(result.get("eligibility_signal", {}))

#     st.markdown("### Final Decision")
#     st.json(result.get("decision", {}))


# def build_chat_context_from_last_result(last_result: dict) -> dict:
#     """
#     Build the unified context required by chatagent.py
#     """
#     extracted_docs = (last_result or {}).get("extracted_docs", {}) or {}
#     decision_output = (last_result or {}).get("decision", {}) or {}
#     validation_output = (last_result or {}).get("validation", {}) or {}
#     eligibility_signal = (last_result or {}).get("eligibility_signal", {}) or {}

#     return {
#         "extracted_docs": extracted_docs,
#         "validation": validation_output,
#         "eligibility_signal": eligibility_signal,
#         "decision": decision_output,
#     }


# def push_user_message(text: str):
#     st.session_state["messages"].append({"role": "user", "content": text})


# def push_assistant_message(text: str):
#     st.session_state["messages"].append({"role": "assistant", "content": text})


# # def render_suggested_questions():
# #     st.markdown("### Suggested questions")
# #     cols = st.columns(3)
# #     for i, q in enumerate(SUGGESTED_QUESTIONS):
# #         if cols[i % 3].button(q, key=f"sugg_{i}"):
# #             push_user_message(q)
# #             st.session_state["pending_user_msg"] = q  # 👈 queue it for backend processing
# #             st.rerun()

# def render_chat_ui():
#     st.subheader("Interactive Chat")

#     last = st.session_state.get("last_result")
#     if not last:
#         st.info("Run the workflow first, then chat here.")
#         return

#     # Chat controls
#     c1, c2, c3 = st.columns([1, 1, 2])
#     with c1:
#         mode = st.selectbox("Mode", ["short", "detailed", "audit"], index=1)
#     with c2:
#         if st.button("Clear chat"):
#             st.session_state["messages"] = []
#             st.rerun()
#     with c3:
#         st.caption("Tip: Use 'audit' mode to get doc-based explanations.")

#     # render_suggested_questions()
#     # process_pending_chat(mode)

#     # Display history
#     for m in st.session_state["messages"]:
#         with st.chat_message(m["role"]):
#             st.write(m["content"])

#     # Input
#     user_msg = st.chat_input("Ask about this application...")
#     if not user_msg:
#         return

#     push_user_message(user_msg)

#     context = build_chat_context_from_last_result(last)
#     history = st.session_state.get("messages", [])

#     try:
#         answer = chat_agent(
#             context=context,
#             question=user_msg,
#             chat_history=history,
#             mode=mode,
#         )
#     except Exception as e:
#         answer = f"Chat error: {e}"

#     push_assistant_message(answer)
#     st.rerun()

# def process_pending_chat(mode: str):
#     """
#     If a suggested question (or any pending question) exists, run chat_agent and append response.
#     """
#     last = st.session_state.get("last_result")
#     pending = st.session_state.get("pending_user_msg")

#     if not last or not pending:
#         return

#     context = build_chat_context_from_last_result(last)
#     history = st.session_state.get("messages", [])

#     try:
#         answer = chat_agent(
#             context=context,
#             question=pending,
#             chat_history=history,
#             mode=mode
#         )
#     except Exception as e:
#         answer = f"Chat error: {e}"

#     push_assistant_message(answer)

#     # clear pending so it doesn't re-run forever
#     # st.session_state["pending_user_msg"] = None

# def save_to_db_or_warn(out: dict):
#     try:
#         from db import store_workflow_output
#         app_id = store_workflow_output(out, model_name=os.getenv("AZURE_OPENAI_DEPLOYMENT"))
#         st.success(f"Saved to DB for application_id={app_id}")
#     except Exception as e:
#         st.warning(f"Workflow completed but DB save failed: {e}")

# def start_langfuse_trace(uploaded_docs: dict) -> str:
#     """
#     Creates a Langfuse trace per workflow run.
#     Returns trace_id.
#     """
#     lf = get_langfuse()

#     # you can set a stable user_id if you have it; otherwise keep generic
#     user_id = "streamlit-user"

#     # light metadata only (avoid uploading entire documents)
#     doc_types = list(uploaded_docs.keys()) if uploaded_docs else []
#     trace = lf.trace(
#         name="social-support-workflow",
#         user_id=user_id,
#         metadata={
#             "doc_types": doc_types,
#             "app_version": "poc-v1",
#         },
#     )
#     return trace.id


# def end_langfuse_trace(trace_id: str, status: str, extra: dict | None = None):
#     lf = get_langfuse()
#     lf.event(
#         trace_id=trace_id,
#         name="workflow.finished",
#         metadata={"status": status, **(extra or {})},
#     )
#     lf.flush()


# def langfuse_log_workflow_outputs(trace_id: str, out: dict):
#     """
#     Logs key signals as events/scores. Keep it small and structured.
#     """
#     lf = get_langfuse()

#     decision = (out or {}).get("decision", {}) or {}
#     validation = (out or {}).get("validation", {}) or {}
#     elig = (out or {}).get("eligibility_signal", {}) or {}
#     vs = validation.get("validation_summary", {}) or {}

#     lf.event(
#         trace_id=trace_id,
#         name="workflow.outputs",
#         metadata={
#             "application_id": decision.get("application_id"),
#             "decision": decision.get("decision"),
#             "eligibility_status": elig.get("eligibility_status"),
#             "validation_high": vs.get("high", 0),
#             "validation_medium": vs.get("medium", 0),
#             "validation_low": vs.get("low", 0),
#             "validation_total": vs.get("total", 0),
#         },
#     )

#     # Optional scores (good for dashboards)
#     conf = decision.get("confidence")
#     if isinstance(conf, (int, float)):
#         lf.score(trace_id=trace_id, name="decision_confidence", value=float(conf))
#     if isinstance(vs.get("high"), int):
#         lf.score(trace_id=trace_id, name="validation_high_count", value=float(vs["high"]))

#     lf.flush()


# # ----------------------------
# # Main
# # ----------------------------

# def main():
#     load_dotenv()
#     init_session_state()

#     st.set_page_config(page_title="Social Support PoC", layout="wide")
#     st.title("Social Support Application — PoC (LangGraph + Azure OpenAI)")

#     # Sidebar build uploads
#     uploaded_docs = build_uploaded_docs_from_sidebar()
#     st.session_state["uploaded_docs"] = uploaded_docs

#     run_btn = st.sidebar.button("Run Workflow", type="primary")

#     # Main layout
#     col1, col2 = st.columns([1, 1])

#     with col1:
#         render_uploaded_preview(uploaded_docs)

#     with col2:        
#         if run_btn:
#             if validate_env_or_show_error() and uploaded_docs:
#                 trace_id = None
#                 try:
#                     # 1) Start trace
#                     trace_id = start_langfuse_trace(uploaded_docs)
#                     st.session_state["trace_id"] = trace_id  # store for chat layer if needed

#                     # 2) Run workflow WITH trace_id in state
#                     t0 = time.time()
#                     # out = run_workflow({**uploaded_docs})  # keep your existing call
#                     out = run_workflow({**uploaded_docs}, trace_id=trace_id)

#                     elapsed_ms = int((time.time() - t0) * 1000)

#                     # If your run_workflow accepts state dict, prefer this instead:
#                     # out = app.invoke({"uploaded_docs": uploaded_docs, "trace_id": trace_id})

#                     # 3) Save decision summary etc. (your existing logic)
#                     out["decision_summary"] = summarize_decision(out)
#                     st.session_state["last_result"] = out
#                     save_to_db_or_warn(out)

#                     # 4) Log outputs to Langfuse
#                     langfuse_log_workflow_outputs(trace_id, out)

#                     # 5) Mark trace done
#                     end_langfuse_trace(trace_id, "SUCCESS", {"elapsed_ms": elapsed_ms})

#                     st.success(f"Workflow complete. Trace ID: {trace_id}")

#                 except Exception as e:
#                     # Log failure to Langfuse
#                     if trace_id:
#                         lf = get_langfuse()
#                         lf.event(
#                             trace_id=trace_id,
#                             name="workflow.error",
#                             metadata={
#                                 "error": str(e),
#                                 "stack": traceback.format_exc()[:8000],
#                             },
#                         )
#                         end_langfuse_trace(trace_id, "ERROR")

#                     st.exception(e)

#         render_workflow_output(st.session_state.get("last_result"))

#     # ✅ show summary between workflow output and chat
#     st.divider()
#     render_decision_summary(st.session_state.get("last_result"))

#     st.divider()
#     render_chat_ui()


# if __name__ == "__main__":
#     main()
