from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import date


class PayrollAnalysisRequest(BaseModel):
    """Request model for payroll analysis"""
    start_date: str = Field(..., description="Start date in YYYY-MM-DD format")
    end_date: str = Field(..., description="End date in YYYY-MM-DD format")
    exclude_holidays: Optional[List[str]] = Field(default=[], description="List of holiday dates in YYYY-MM-DD format")
    
    class Config:
        json_schema_extra = {
            "example": {
                "start_date": "2025-11-17",
                "end_date": "2025-11-23",
                "exclude_holidays": ["2025-11-20"]
            }
        }


class ExcessHoursEntry(BaseModel):
    """Model for excess hours entry"""
    Name: str
    Date: str
    Total_Hours: float


class RestHoursEntry(BaseModel):
    """Model for rest hours entry"""
    Name: str
    Date: str
    Rest_Hours: float


class WeeklyHoursEntry(BaseModel):
    """Model for weekly hours entry"""
    Name: str
    Week_Start: str
    Week_End: str
    Total_Weekly_Hours: float


class WorkingDaysEntry(BaseModel):
    """Model for working days entry"""
    Name: str
    Days_Worked: int
    First_Day: str
    Last_Day: str


class PayrollAnalysisResponse(BaseModel):
    """Response model for payroll analysis"""
    flagged_excess_hours: List[ExcessHoursEntry] = Field(default=[], description="Persons with punch time exceeding 12 hours")
    flagged_low_rest_hours: List[RestHoursEntry] = Field(default=[], description="Persons with rest hours less than 10")
    flagged_weekly_excess: List[WeeklyHoursEntry] = Field(default=[], description="Persons working 60+ hours per week")
    flagged_excess_days: List[WorkingDaysEntry] = Field(default=[], description="Persons working more than 6 days")
    
    class Config:
        json_schema_extra = {
            "example": {
                "flagged_excess_hours": [
                    {
                        "Name": "JOHN DOE",
                        "Date": "2025-11-16",
                        "Total_Hours": 12.5
                    }
                ],
                "flagged_low_rest_hours": [],
                "flagged_weekly_excess": [],
                "flagged_excess_days": []
            }
        }

