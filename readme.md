# Social Support Application Workflow Automation (PoC)

This repository contains a **Streamlit + LangGraph based prototype** that automates a government-style social support application workflow using **agentic AI** and **multimodal document processing**.

The system ingests an application form and supporting documents, extracts structured data, validates inconsistencies, determines eligibility, produces a final decision, recommends economic enablement support, and provides an interactive chatbot to explain outcomes.

---

## Key Features

- Interactive **Streamlit UI**
- **LangGraph**-based agent orchestration
- Multimodal document ingestion (PDF, TXT, PNG/JPG)
- Rule-based validation for auditability
- Eligibility assessment and decisioning:
  - APPROVE
  - NEEDS_REVIEW
  - SOFT_DECLINE
- Economic enablement recommendations:
  - Upskilling / training
  - Job matching
  - Career / financial counseling
- Decision summary (human-readable, 3–4 lines)
- Interactive chatbot to ask questions about the decision
- PostgreSQL persistence (relational + JSONB)

---

## Prerequisites

- Python **3.10+** (recommended: 3.11)
- Docker (for PostgreSQL)
- Azure OpenAI access (GPT-4o deployment)

---

1. Create & Activate Virtual Environment

### macOS / Linux
```bash
python3 -m venv venv
source venv/bin/activate
```

2. Install Dependencies
```bash
pip install -r requirements.txt
```

3. Configure Environment Variables
```bash
# Create a .env file in the project root:
# Azure OpenAI
AZURE_OPENAI_API_KEY=your_key
AZURE_OPENAI_API_BASE=https://<your-resource>.openai.azure.com/
AZURE_OPENAI_API_VERSION=2024-12-01-preview
AZURE_OPENAI_DEPLOYMENT=gpt-4o-deployment-name

# PostgreSQL
DATABASE_URL=postgresql://govuser:govpass@localhost:5432/govdb
```

4. Start PostgreSQL (Docker)
```bash
docker run --name gov-postgres \
  -e POSTGRES_USER=govuser \
  -e POSTGRES_PASSWORD=govpass \
  -e POSTGRES_DB=govdb \
  -p 5432:5432 \
  -d postgres:16
```

Verify:

```bash
docker ps
```

5. Create Database Schema
```bash
docker exec -i gov-postgres psql -U govuser -d govdb < schema.sql
```

6. Run the Application
```bash
streamlit run app.py
```

Open in browser:
```bash
http://localhost:8501
```


