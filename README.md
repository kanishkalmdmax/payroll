# Payroll Analysis (FastAPI + UI)

This repo hosts:
- A FastAPI backend that analyzes payroll punch data and flags:
  - Excess daily hours (>12)
  - Low rest hours between shifts (<10)
  - Weekly excess hours (>=60)
  - Excess working days per week (>6)
- A lightweight web UI to upload files and view/download results.

## Expected CSV headers

`EECode, Firstname, Lastname, InPunchTime, OutPunchTime`

Dates/times can be any format Pandas can parse (recommended: `YYYY-MM-DD HH:MM:SS`).

## Run locally

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate

pip install -r requirements.txt
uvicorn payroll_api.main:app --reload
```

Open: http://127.0.0.1:8000

> If your port differs, set `--port`.

## API

- `POST /payroll/analyze` (multipart/form-data)
  - file: .csv or .xlsx
  - start_date: YYYY-MM-DD
  - end_date: YYYY-MM-DD
  - exclude_holidays: comma-separated YYYY-MM-DD list (optional)
- `GET /payroll/report/{request_id}` downloads the generated Excel report.

## Debugging

Set log level via env var:

```bash
export LOG_LEVEL=DEBUG
```

Every response includes `request_id`. Search that ID in Render logs to trace the full pipeline.

## Render deployment

**Start command** (Render Web Service):

```bash
uvicorn payroll_api.main:app --host 0.0.0.0 --port $PORT
```

**Environment variables**
- `LOG_LEVEL=INFO` (or `DEBUG`)
- `ALLOWED_ORIGINS=https://<your-render-url>` (optional)
- `REPORT_DIR=/tmp/payroll_reports` (default)

Render uses an ephemeral filesystem; reports are stored under `/tmp`.
