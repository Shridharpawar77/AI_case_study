import os
import json
import uuid
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

import psycopg
from psycopg.rows import dict_row


# -----------------------------
# Connection
# -----------------------------
def get_conn():
    """
    Requires DATABASE_URL like:
      postgresql://user:pass@host:5432/dbname
    """
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        raise RuntimeError("DATABASE_URL is missing. Set it in .env or your shell.")
    return psycopg.connect(dsn)


# -----------------------------
# Schema bootstrap (no migrations needed for PoC)
# -----------------------------
DDL = [
    """
    CREATE TABLE IF NOT EXISTS applications (
      id BIGSERIAL PRIMARY KEY,
      application_id TEXT UNIQUE NOT NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      applicant_name TEXT,
      emirates_id TEXT,
      date_of_birth TEXT,
      requested_product TEXT,
      payload JSONB NOT NULL DEFAULT '{}'::jsonb
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_applications_application_id ON applications(application_id);",
    """
    CREATE TABLE IF NOT EXISTS document_extractions (
      id BIGSERIAL PRIMARY KEY,
      application_id TEXT NOT NULL REFERENCES applications(application_id) ON DELETE CASCADE,
      doc_type TEXT NOT NULL,
      filename TEXT,
      model_name TEXT,
      extracted_fields JSONB NOT NULL DEFAULT '{}'::jsonb,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      UNIQUE(application_id, doc_type, COALESCE(filename, ''))
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_doc_extract_appid ON document_extractions(application_id);",
    """
    CREATE TABLE IF NOT EXISTS validations (
      id BIGSERIAL PRIMARY KEY,
      application_id TEXT NOT NULL REFERENCES applications(application_id) ON DELETE CASCADE,
      validation JSONB NOT NULL DEFAULT '{}'::jsonb,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_validations_appid ON validations(application_id);",
    """
    CREATE TABLE IF NOT EXISTS decisions (
      id BIGSERIAL PRIMARY KEY,
      application_id TEXT NOT NULL REFERENCES applications(application_id) ON DELETE CASCADE,
      decision JSONB NOT NULL DEFAULT '{}'::jsonb,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_decisions_appid ON decisions(application_id);",
]


def ensure_schema(conn: psycopg.Connection) -> None:
    """
    Creates the minimal tables needed for this PoC.
    Safe to call on every run (IF NOT EXISTS).
    """
    with conn.cursor() as cur:
        for stmt in DDL:
            cur.execute(stmt)
    conn.commit()


# -----------------------------
# Helpers
# -----------------------------
def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _gen_app_id() -> str:
    # Keep it readable but unique enough for PoC
    return f"APP-{uuid.uuid4().hex[:10].upper()}"


def _extract_application_core(extracted_docs: Dict[str, Any]) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """
    Best-effort pull common fields from extracted_docs.
    """
    app = extracted_docs.get("APPLICATION_FORM", {}) or {}
    eid = extracted_docs.get("EMIRATES_ID", {}) or {}

    applicant_name = (
        app.get("full_name")
        or app.get("name")
        or eid.get("full_name")
        or eid.get("name")
    )
    emirates_id = eid.get("emirates_id") or eid.get("id_number")
    dob = eid.get("date_of_birth") or app.get("date_of_birth")
    requested_product = app.get("requested_product") or app.get("product")

    return applicant_name, emirates_id, dob, requested_product


# -----------------------------
# Writes
# -----------------------------
def upsert_application(cur: psycopg.Cursor, extracted_docs: Dict[str, Any], application_id: Optional[str] = None) -> str:
    """
    Creates/updates one row in applications.
    - Uses provided application_id if present, else tries extracted_docs, else generates.
    - Stores extracted_docs (and later full workflow payload) in payload JSONB.
    """
    # Try to find an application id from payloads
    if not application_id:
        app = extracted_docs.get("APPLICATION_FORM", {}) or {}
        application_id = app.get("application_id") or app.get("id")

    if not application_id:
        application_id = _gen_app_id()

    applicant_name, emirates_id, dob, requested_product = _extract_application_core(extracted_docs)

    cur.execute(
        """
        INSERT INTO applications (application_id, applicant_name, emirates_id, date_of_birth, requested_product, payload, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s::jsonb, NOW())
        ON CONFLICT (application_id) DO UPDATE SET
          applicant_name = EXCLUDED.applicant_name,
          emirates_id = EXCLUDED.emirates_id,
          date_of_birth = EXCLUDED.date_of_birth,
          requested_product = EXCLUDED.requested_product,
          payload = applications.payload || EXCLUDED.payload,
          updated_at = NOW()
        RETURNING application_id;
        """,
        (
            application_id,
            applicant_name,
            emirates_id,
            dob,
            requested_product,
            json.dumps({"extracted_docs": extracted_docs, "last_updated": _now_iso()}),
        ),
    )
    row = cur.fetchone()
    return row[0]


def upsert_document_extractions(
    cur: psycopg.Cursor,
    application_id: str,
    extracted_docs: Dict[str, Any],
    model_name: Optional[str] = None,
) -> None:
    """
    Stores per-document extracted fields in document_extractions.
    extracted_docs is expected like:
      { "EMIRATES_ID": {...}, "BANK_STATEMENT": {...}, ... }
    """
    for doc_type, extracted in (extracted_docs or {}).items():
        if extracted is None:
            extracted = {}
        filename = None
        # allow both dict or list formats
        if isinstance(extracted, dict):
            filename = extracted.get("filename")
            extracted_fields = extracted
        else:
            extracted_fields = {"value": extracted}

        cur.execute(
            """
            INSERT INTO document_extractions (application_id, doc_type, filename, model_name, extracted_fields)
            VALUES (%s, %s, %s, %s, %s::jsonb)
            ON CONFLICT (application_id, doc_type, COALESCE(filename, '')) DO UPDATE SET
              model_name = EXCLUDED.model_name,
              extracted_fields = EXCLUDED.extracted_fields,
              created_at = NOW();
            """,
            (application_id, doc_type, filename, model_name, json.dumps(extracted_fields)),
        )


def insert_validation(cur: psycopg.Cursor, application_id: str, validation: Dict[str, Any]) -> None:
    cur.execute(
        "INSERT INTO validations (application_id, validation) VALUES (%s, %s::jsonb);",
        (application_id, json.dumps(validation or {})),
    )


def insert_decision(cur: psycopg.Cursor, application_id: str, decision: Dict[str, Any]) -> None:
    cur.execute(
        "INSERT INTO decisions (application_id, decision) VALUES (%s, %s::jsonb);",
        (application_id, json.dumps(decision or {})),
    )

def store_workflow_output(workflow_output: Dict[str, Any], model_name: Optional[str] = None) -> str:
    """
    Main entry-point called by your workflow.
    Ensures schema exists (so you don't get 'relation does not exist'),
    then writes:
      - applications (upsert)
      - document_extractions (upsert)
      - validations (append)
      - decisions (append)
    """
    extracted_docs = workflow_output.get("extracted_docs", {}) or {}
    validation = workflow_output.get("validation", {}) or {}
    decision = workflow_output.get("decision", {}) or {}

    with get_conn() as conn:
        ensure_schema(conn)  # ✅ fixes: relation "applications" does not exist
        with conn.cursor() as cur:
            application_id = workflow_output.get("application_id") or None
            application_id = upsert_application(cur, extracted_docs, application_id=application_id)

            # Store full workflow output in applications.payload as well
            cur.execute(
                """
                UPDATE applications
                SET payload = payload || %s::jsonb,
                    updated_at = NOW()
                WHERE application_id = %s;
                """,
                (json.dumps({"workflow_output": workflow_output, "last_saved": _now_iso()}), application_id),
            )

            upsert_document_extractions(cur, application_id, extracted_docs, model_name=model_name)
            insert_validation(cur, application_id, validation)
            insert_decision(cur, application_id, decision)

        conn.commit()

    return application_id
