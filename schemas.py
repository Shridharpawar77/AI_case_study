DOCUMENT_SCHEMAS = {
    "APPLICATION_FORM": {
        "application_id": "string",
        "applicant_name": "string",
        "declared_monthly_income": "number",
        "family_size": "number",
        "employment_status": "string",
        "_extraction_notes": "string"
    },

    "EMIRATES_ID": {
        "full_name": "string",
        "emirates_id": "string",
        "address": "string",
        "date_of_birth": "string",
        "_extraction_notes": "string"
    },

    "BANK_STATEMENT": {
        "statement_period": "string",
        "monthly_income": "number",
        "average_balance": "number",
        "employer_name": "string",
        "_extraction_notes": "string"
    },

    "CREDIT_REPORT": {
        "credit_score": "number",
        "total_liabilities": "number",
        "active_loans": "number",
        "_extraction_notes": "string"
    },

    "ASSETS_LIABILITIES": {
        "total_assets": "number",
        "total_liabilities": "number",
        "net_worth": "number",
        "_extraction_notes": "string"
    },

    "RESUME": {
        "current_employer": "string",
        "years_of_experience": "number",
        "current_role": "string",
        "_extraction_notes": "string"
    }
}
