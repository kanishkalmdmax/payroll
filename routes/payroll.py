from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from models.schemas import PayrollAnalysisResponse
from services.payroll_service import PayrollService
import os
import tempfile
from typing import Optional

router = APIRouter(prefix="/payroll", tags=["Payroll Analysis"])


@router.post("/analyze", response_model=PayrollAnalysisResponse)
async def analyze_payroll(
    file: UploadFile = File(..., description="Excel file (.xlsx) containing payroll data"),
    start_date: str = Form(..., description="Start date in YYYY-MM-DD format"),
    end_date: str = Form(..., description="End date in YYYY-MM-DD format"),
    exclude_holidays: Optional[str] = Form(None, description="Comma-separated holiday dates in YYYY-MM-DD format (e.g., '2025-11-20,2025-11-25')")
):
    """
    Analyze payroll data and flag violations
    
    This endpoint analyzes payroll data and flags:
    - Persons with punch time exceeding 12 hours
    - Persons with rest hours less than 10
    - Persons working 60+ hours per week
    - Persons working more than 6 days (excluding specified holidays)
    
    Args:
        file: Excel file containing payroll data
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
        exclude_holidays: Comma-separated holiday dates (optional)
    
    Returns:
        PayrollAnalysisResponse with all flagged entries
    """
    # Validate file type
    if not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(
            status_code=400, 
            detail="Invalid file type. Please upload an Excel file (.xlsx or .xls)"
        )
    
    # Create a temporary file to store the uploaded Excel file
    temp_file = None
    try:
        # Create temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as temp_file:
            # Read uploaded file content
            content = await file.read()
            temp_file.write(content)
            temp_file_path = temp_file.name
        
        # Parse exclude_holidays from comma-separated string to list
        holidays_list = []
        if exclude_holidays:
            holidays_list = [h.strip() for h in exclude_holidays.split(',') if h.strip()]
        
        # Initialize service with temporary file
        service = PayrollService(temp_file_path)
        
        # Perform analysis
        result = service.analyze_payroll(
            start_date=start_date,
            end_date=end_date,
            exclude_holidays=holidays_list
        )
        
        return PayrollAnalysisResponse(**result)
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid input: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
    finally:
        # Clean up temporary file
        if temp_file and os.path.exists(temp_file_path):
            try:
                os.unlink(temp_file_path)
            except Exception:
                pass


@router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "Payroll Analysis API"
    }

