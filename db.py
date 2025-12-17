import os
import json
from typing import Any, Dict, Optional
import psycopg

def get_conn():
    # Prefer DATABASE_URL like: postgresql://user:pass@localhost:5432/dbname
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        raise RuntimeError("DATABASE_URL is missing")
    return psycopg.connect(dsn)

def upsert_application(cur, extracted_docs: Dict[str, Any]) -> str:
    app = extracted_docs.get("APPLICATION_FORM", {}) or {}
    eid = extracted_docs.get("EMIRATES_ID", {}) or {}

    application_id = app.get("application_id") or "UNKNOWN_APP"
    applicant_name = app.get("applicant_name") or eid.get("full_name")
    emirates_id = eid.get("emirates_id")

    declared_income = app.get("declared_monthly_income")
    family_size = app.get("family_size")
    employment_status = app.get("employment_status")

    cur.execute("""
        INSERT INTO applications (
          application_id, applicant_name, emirates_id, status,
          declared_monthly_income, family_size, employment_status
        )
        VALUES (%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (application_id) DO UPDATE SET
          applicant_name = EXCLUDED.applicant_name,
          emirates_id = EXCLUDED.emirates_id,
          declared_monthly_income = EXCLUDED.declared_monthly_income,
          family_size = EXCLUDED.family_size,
          employment_status = EXCLUDED.employment_status,
          updated_at = now()
        RETURNING application_id
    """, (
        application_id, applicant_name, emirates_id, "PROCESSED",
        declared_income, family_size, employment_status
    ))
    return cur.fetchone()[0]

def upsert_document_extractions(cur, application_id: str, extracted_docs: Dict[str, Any], model_name: Optional[str] = None):
    for doc_type, payload in (extracted_docs or {}).items():
        if not isinstance(payload, dict):
            continue
        notes = payload.get("_extraction_notes")
        cur.execute("""
            INSERT INTO document_extractions (application_id, doc_type, extracted_json, extraction_notes, model)
            VALUES (%s,%s,%s,%s,%s)
            ON CONFLICT (application_id, doc_type) DO UPDATE SET
              extracted_json = EXCLUDED.extracted_json,
              extraction_notes = EXCLUDED.extraction_notes,
              model = EXCLUDED.model,
              created_at = now()
        """, (
            application_id, doc_type, json.dumps(payload), notes, model_name
        ))

def insert_validation(cur, application_id: str, validation: Dict[str, Any]) -> int:
    summary = validation.get("validation_summary") or {}
    issues = validation.get("issues") or []

    cur.execute("""
        INSERT INTO validation_runs (application_id, summary_json)
        VALUES (%s, %s)
        RETURNING id
    """, (application_id, json.dumps(summary)))
    run_id = cur.fetchone()[0]

    for i in issues:
        cur.execute("""
            INSERT INTO validation_issues (
              validation_run_id, issue_type, severity, description, source, field, sources, suggestion
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            run_id,
            i.get("type") or i.get("code") or "UNKNOWN",
            i.get("severity") or "MEDIUM",
            i.get("description") or i.get("message") or "",
            i.get("source"),
            i.get("field"),
            json.dumps(i.get("sources")) if i.get("sources") is not None else None,
            i.get("suggestion"),
        ))

    return run_id

def insert_decision(cur, application_id: str, decision: Dict[str, Any]) -> int:
    cur.execute("""
        INSERT INTO decisions (
          application_id, decision, confidence, reasons, next_steps, decision_json
        )
        VALUES (%s,%s,%s,%s,%s,%s)
        RETURNING id
    """, (
        application_id,
        decision.get("decision"),
        decision.get("confidence"),
        json.dumps(decision.get("reasons") or []),
        json.dumps(decision.get("next_steps") or []),
        json.dumps(decision)
    ))
    decision_id = cur.fetchone()[0]

    for rec in (decision.get("enablement_recommendations") or []):
        cur.execute("""
            INSERT INTO enablement_recommendations (decision_id, category, recommendation, reason)
            VALUES (%s,%s,%s,%s)
        """, (
            decision_id,
            rec.get("category"),
            rec.get("recommendation"),
            rec.get("reason"),
        ))

    return decision_id

def store_workflow_output(workflow_output: Dict[str, Any], model_name: Optional[str] = None) -> str:
    extracted_docs = workflow_output.get("extracted_docs", {}) or {}
    validation = workflow_output.get("validation", {}) or {}
    decision = workflow_output.get("decision", {}) or {}

    with get_conn() as conn:
        with conn.cursor() as cur:
            application_id = upsert_application(cur, extracted_docs)
            upsert_document_extractions(cur, application_id, extracted_docs, model_name=model_name)
            insert_validation(cur, application_id, validation)
            insert_decision(cur, application_id, decision)
        conn.commit()

    return application_id
