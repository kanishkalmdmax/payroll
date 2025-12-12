import logging
import os
import tempfile
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse

from ..models.schemas import PayrollAnalysisResponse
from ..services.payroll_service import PayrollService

logger = logging.getLogger("payroll_api.routes")

router = APIRouter(prefix="/payroll", tags=["Payroll Analysis"])

REPORT_DIR = os.getenv("REPORT_DIR", "/tmp/payroll_reports")

def _safe_request_id() -> str:
    return "req_" + uuid.uuid4().hex[:12]

@router.post("/analyze", response_model=PayrollAnalysisResponse)
async def analyze_payroll(
    file: UploadFile = File(..., description="Payroll file (.csv or .xlsx)"),
    start_date: str = Form(..., description="Start date in YYYY-MM-DD format"),
    end_date: str = Form(..., description="End date in YYYY-MM-DD format"),
    exclude_holidays: Optional[str] = Form(
        None,
        description="Comma-separated holiday dates in YYYY-MM-DD format (e.g., '2025-11-20,2025-11-25')"
    ),
):
    request_id = _safe_request_id()
    logger.info("[%s] analyze request received filename=%s content_type=%s", request_id, file.filename, file.content_type)

    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided.")

    filename_lower = file.filename.lower()
    if not (filename_lower.endswith(".csv") or filename_lower.endswith(".xlsx") or filename_lower.endswith(".xlsm") or filename_lower.endswith(".xltx") or filename_lower.endswith(".xltm")):
        raise HTTPException(status_code=400, detail="Unsupported file type. Please upload a .csv or .xlsx file.")

    # Parse exclude_holidays from comma-separated string to list
    holidays_list = []
    if exclude_holidays:
        holidays_list = [h.strip() for h in exclude_holidays.split(",") if h.strip()]

    temp_path = None
    try:
        suffix = os.path.splitext(filename_lower)[1]
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            content = await file.read()
            if not content:
                raise HTTPException(status_code=400, detail="Uploaded file is empty.")
            tmp.write(content)
            temp_path = tmp.name

        logger.info("[%s] temp_file_written=%s size_bytes=%s", request_id, temp_path, len(content))

        df = PayrollService.load_file(temp_path)
        service = PayrollService(df)

        result = service.analyze(
            start_date=start_date,
            end_date=end_date,
            exclude_holidays=holidays_list,
            report_dir=REPORT_DIR,
            request_id=request_id,
        )

        download_url = None
        if result.report_path and os.path.exists(result.report_path):
            download_url = f"/payroll/report/{request_id}"

        return PayrollAnalysisResponse(
            request_id=request_id,
            summary=result.data["summary"],
            flagged_excess_hours=result.data["flagged_excess_hours"],
            flagged_low_rest_hours=result.data["flagged_low_rest_hours"],
            flagged_weekly_excess=result.data["flagged_weekly_excess"],
            flagged_excess_days=result.data["flagged_excess_days"],
            download_url=download_url,
            warnings=result.warnings,
        )

    except HTTPException:
        raise
    except ValueError as e:
        # Known validation issue
        logger.exception("[%s] validation_error", request_id)
        raise HTTPException(status_code=400, detail=f"{e} (request_id={request_id})")
    except Exception as e:
        logger.exception("[%s] unexpected_error", request_id)
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e} (request_id={request_id})")
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except Exception:
                logger.warning("[%s] failed_to_delete_temp=%s", request_id, temp_path)

@router.get("/report/{request_id}")
async def download_report(request_id: str):
    path = os.path.join(REPORT_DIR, f"payroll_report_{request_id}.xlsx")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Report not found (it may have expired or generation failed).")
    return FileResponse(
        path,
        filename=f"payroll_report_{request_id}.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

@router.get("/health")
async def health_check():
    return {"status": "healthy", "service": "Payroll Analysis API"}
