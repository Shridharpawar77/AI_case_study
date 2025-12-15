# AI Case Study – Social Support Application Workflow Automation (Prototype)

Prototype AI workflow to automate social support application assessment using locally hosted ML + LLM, multimodal document ingestion, agentic orchestration, and an interactive Streamlit UI.

## What this prototype does (Day 1 – MVP)
- Streamlit UI to submit:
  - Applicant form data (basic fields)
  - Attachments (optional for Day 1; stubbed parsing)
- FastAPI backend `/apply` endpoint
- Agentic workflow (LangGraph skeleton) that:
  1) Extracts/normalizes applicant profile (stub)
  2) Runs basic validations (stub)
  3) Runs eligibility scoring (stub or simple rule)
  4) Returns decision + short explanation
- Locally hosted LLM via Ollama (optional on Day 1; c
