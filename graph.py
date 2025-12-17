from typing import TypedDict, Dict, Any
from langgraph.graph import StateGraph, END

from agents.ingestionagent import ingestion_agent
from agents.extractionagent_ollama import extraction_agent
from agents.validationagent import validation_agent
from agents.eligibilityagent import eligibility_agent
from agents.decisionagent_ollama import decision_agent


class AppState(TypedDict, total=False):
    # Inputs
    model: str  # (optional) kept for future; Azure uses DEPLOYMENT_NAME in llmclient.py
    uploaded_docs: Dict[str, Any]  # {doc_type: {"filename":..., "text":..., "file_bytes":...}}

    # Intermediate
    ingested_docs: Dict[str, Any]   # normalized multimodal docs
    extracted_docs: Dict[str, Any]  # {doc_type: extracted_json}
    validation: Dict[str, Any]      # validation result
    eligibility_signal: Dict[str, Any]  # rule-based eligibility assessment

    # Output
    decision: Dict[str, Any]


def node_ingest(state: AppState) -> AppState:
    state["ingested_docs"] = ingestion_agent(state.get("uploaded_docs", {}))
    return state


def node_extract(state: AppState) -> AppState:
    ingested = state.get("ingested_docs", {}) or {}
    extracted: Dict[str, Any] = {}

    for doc_type, payload in ingested.items():
        # payload contains content_type and either document_text or image_base64
        extracted[doc_type] = extraction_agent(payload)

    state["extracted_docs"] = extracted
    return state


def node_validate(state: AppState) -> AppState:
    state["validation"] = validation_agent(state.get("extracted_docs", {}) or {})
    return state

def node_eligibility(state: AppState) -> AppState:
    state["eligibility_signal"] = eligibility_agent(state.get("extracted_docs", {}) or {})
    return state

def node_decide(state: AppState) -> AppState:
    extracted = state.get("extracted_docs", {}) or {}
    validation = state.get("validation", {}) or {}
    eligibility = state.get("eligibility_signal", {}) or {}

    state["decision"] = decision_agent(extracted, validation, eligibility)
    return state


def build_graph():
    g = StateGraph(AppState)

    g.add_node("ingest", node_ingest)
    g.add_node("extract", node_extract)
    g.add_node("validate", node_validate)
    g.add_node("eligibility", node_eligibility)
    g.add_node("decide", node_decide)

    g.set_entry_point("ingest")

    g.add_edge("ingest", "extract")
    g.add_edge("extract", "validate")
    g.add_edge("validate", "eligibility")
    g.add_edge("eligibility", "decide")
    g.add_edge("decide", END)

    return g.compile()
