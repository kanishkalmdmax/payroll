from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class FlaggedExcessHours(BaseModel):
    EECode: str
    Firstname: str
    Lastname: str
    Date: str
    Hours_Worked: float

class FlaggedLowRestHours(BaseModel):
    EECode: str
    Firstname: str
    Lastname: str
    Date: str
    Rest_Hours: float

class FlaggedWeeklyExcess(BaseModel):
    EECode: str
    Firstname: str
    Lastname: str
    Week_Start: str
    Week_End: str
    Total_Hours: float

class FlaggedExcessDays(BaseModel):
    EECode: str
    Firstname: str
    Lastname: str
    Week_Start: str
    Week_End: str
    Days_Worked: int

class PayrollAnalysisResponse(BaseModel):
    request_id: str = Field(..., description="Use this ID to correlate backend logs for debugging")
    summary: Dict[str, Any] = Field(..., description="Counts + basic stats")
    flagged_excess_hours: List[FlaggedExcessHours]
    flagged_low_rest_hours: List[FlaggedLowRestHours]
    flagged_weekly_excess: List[FlaggedWeeklyExcess]
    flagged_excess_days: List[FlaggedExcessDays]
    download_url: Optional[str] = Field(None, description="URL to download the generated report file")
    warnings: List[str] = Field(default_factory=list)

    model_config = {
        "json_schema_extra": {
            "example": {
                "request_id": "req_123",
                "summary": {
                    "rows_received": 1200,
                    "rows_after_filter": 800,
                    "employees": 120
                },
                "flagged_excess_hours": [],
                "flagged_low_rest_hours": [],
                "flagged_weekly_excess": [],
                "flagged_excess_days": [],
                "download_url": "/payroll/report/req_123",
                "warnings": []
            }
        }
    }
