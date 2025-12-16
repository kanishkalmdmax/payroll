import pandas as pd
from datetime import datetime, timedelta, date
from typing import List, Optional, Dict, Any
import os
import logging
from dataclasses import dataclass

logger = logging.getLogger("payroll_api.service")

REQUIRED_COLUMNS = ["EECode", "Firstname", "Lastname", "InPunchTime", "OutPunchTime"]

@dataclass
class AnalysisResult:
    """Result object for payroll analysis"""
    data: Dict[str, Any]
    report_path: Optional[str]
    warnings: List[str]


class PayrollService:
    """Service class for payroll analysis operations"""
    
    def __init__(self, file_path: str):
        """
        Initialize the service with the file path (Excel or CSV)
        
        Args:
            file_path: Path to the Excel (.xlsx, .xls) or CSV (.csv) file
        """
        # Detect file type based on extension
        file_extension = os.path.splitext(file_path)[1].lower()
        
        if file_extension in ['.xlsx', '.xls']:
            # Read Excel file
            self.df = pd.read_excel(file_path)
        elif file_extension == '.csv':
            # Read CSV file
            self.df = pd.read_csv(file_path)
        else:
            raise ValueError(f"Unsupported file type: {file_extension}. Supported formats: .xlsx, .xls, .csv")
        
        # Normalize column names to handle different naming conventions
        self._normalize_column_names()
    
    @staticmethod
    def _parse_holidays(exclude_holidays: Optional[List[str]]) -> List[date]:
        """Parse and validate holiday dates"""
        if not exclude_holidays:
            return []
        out = []
        for h in exclude_holidays:
            h = h.strip()
            if not h:
                continue
            try:
                out.append(pd.to_datetime(h, errors="raise").date())
            except Exception:
                raise ValueError(f"Invalid holiday date: '{h}'. Use YYYY-MM-DD, e.g. 2025-12-25")
        return out

    @staticmethod
    def _parse_date_str(d: Optional[str], field_name: str) -> Optional[pd.Timestamp]:
        """Parse and validate date string"""
        if d is None or str(d).strip() == "":
            return None
        try:
            return pd.to_datetime(d, errors="raise")
        except Exception:
            raise ValueError(f"Invalid {field_name}: '{d}'. Use YYYY-MM-DD.")
    
    def _normalize_column_names(self):
        """
        Normalize column names to standardized format
        Handles different naming conventions like 'In time', 'In Time', 'InPunchTime', etc.
        """
        # Strip BOM and whitespace from headers first
        self.df.columns = [str(c).replace("\ufeff", "").strip() for c in self.df.columns]
        
        # Define column name mappings (alternative names -> standard name)
        column_mappings = {
            'InPunchTime': ['In time', 'In Time', 'Intime', 'IN TIME', 'in time', 'In_time', 'InTime', 'In_Time'],
            'OutPunchTime': ['Out time', 'Out Time', 'Outtime', 'OUT TIME', 'out time', 'Out_time', 'OutTime', 'Out_Time'],
            'Firstname': ['First name', 'First Name', 'FirstName', 'FIRSTNAME', 'first name', 'First_name', 'first_name'],
            'Lastname': ['Last name', 'Last Name', 'LastName', 'LASTNAME', 'last name', 'Last_name', 'last_name'],
            'EECode': ['EE Code', 'Company Code', 'EmployeeCode', 'Employee_Code', 'employee_code', 'EECODE', 'ee_code']
        }
        
        # Create a mapping of current column names to standard names
        rename_dict = {}
        current_columns = self.df.columns.tolist()
        
        for standard_name, alternative_names in column_mappings.items():
            # Check if standard name already exists
            if standard_name in current_columns:
                continue
            
            # Look for alternative names
            for alt_name in alternative_names:
                if alt_name in current_columns:
                    rename_dict[alt_name] = standard_name
                    break
        
        # Apply the renaming
        if rename_dict:
            self.df.rename(columns=rename_dict, inplace=True)
        
        # Verify required columns exist
        missing_columns = [col for col in REQUIRED_COLUMNS if col not in self.df.columns]
        
        if missing_columns:
            raise ValueError(f"Missing required columns: {', '.join(missing_columns)}. "
                           f"Available columns: {', '.join(self.df.columns.tolist())}")
    
    def flag_excess_hours(self) -> List[dict]:
        """
        Flag persons with total daily working hours exceeding 12 hours.
        Handles multiple entries per day by summing all hours worked on the same day.
        """
        flagged = []
        
        # Parse datetime columns
        df = self.df.copy()
        df['InPunchTime_dt'] = pd.to_datetime(df['InPunchTime'])
        df['OutPunchTime_dt'] = pd.to_datetime(df['OutPunchTime'])
        df['Date'] = df['InPunchTime_dt'].dt.date
        
        # Calculate hours for each entry
        hours_list = []
        for idx, row in df.iterrows():
            try:
                punch_in = row['InPunchTime_dt']
                punch_out = row['OutPunchTime_dt']
                
                if pd.notna(punch_in) and pd.notna(punch_out):
                    time_diff = punch_out - punch_in
                    
                    if time_diff.total_seconds() < 0:
                        time_diff = time_diff + timedelta(days=1)
                    
                    hours = time_diff.total_seconds() / 3600
                    hours_list.append({
                        'EECode': row['EECode'],
                        'Firstname': row['Firstname'],
                        'Lastname': row['Lastname'],
                        'Date': row['Date'],
                        'Hours': hours
                    })
            except Exception as e:
                print(f"Error processing row {idx}: {e}")
                continue
        
        if not hours_list:
            return flagged
        
        # Convert to DataFrame and sum hours per person per day
        df_hours = pd.DataFrame(hours_list)
        daily_totals = df_hours.groupby(['EECode', 'Firstname', 'Lastname', 'Date']).agg({
            'Hours': 'sum'
        }).reset_index()
        
        # Flag days with total hours > 12
        for idx, row in daily_totals.iterrows():
            if row['Hours'] > 12:
                name = f"{row['Firstname']} {row['Lastname']}"
                flagged.append({
                    'Name': name,
                    'Date': str(row['Date']),
                    'Total_Hours': round(row['Hours'], 2)
                })
        
        return flagged
    
    def flag_low_rest_hours(self) -> List[dict]:
        """
        Flag persons with rest hours less than 10.
        Handles multiple entries per day by calculating rest between:
        - LAST punch out of Day N
        - FIRST punch in of Day N+1
        """
        flagged = []
        
        # Parse datetime columns
        df = self.df.copy()
        df['InPunchTime_dt'] = pd.to_datetime(df['InPunchTime'])
        df['OutPunchTime_dt'] = pd.to_datetime(df['OutPunchTime'])
        df['Date'] = df['InPunchTime_dt'].dt.date
        
        # Group by person and date to get first punch in and last punch out per day
        daily_punches = df.groupby(['EECode', 'Firstname', 'Lastname', 'Date']).agg({
            'InPunchTime_dt': 'min',   # First punch in of the day
            'OutPunchTime_dt': 'max'    # Last punch out of the day
        }).reset_index()
        
        # Sort by person and date
        daily_punches = daily_punches.sort_values(
            ['EECode', 'Lastname', 'Firstname', 'Date']
        ).reset_index(drop=True)
        
        # Calculate rest hours between consecutive days
        for idx in range(1, len(daily_punches)):
            try:
                curr_day = daily_punches.iloc[idx]
                prev_day = daily_punches.iloc[idx - 1]
                
                # Check if same person (EECode, Lastname, Firstname)
                if (curr_day['EECode'] == prev_day['EECode'] and 
                    curr_day['Lastname'] == prev_day['Lastname'] and 
                    curr_day['Firstname'] == prev_day['Firstname']):
                    
                    # Get last punch out of previous day
                    prev_day_last_out = prev_day['OutPunchTime_dt']
                    
                    # Get first punch in of current day
                    curr_day_first_in = curr_day['InPunchTime_dt']
                    
                    if pd.notna(curr_day_first_in) and pd.notna(prev_day_last_out):
                        # Calculate rest hours
                        rest_diff = curr_day_first_in - prev_day_last_out
                        rest_hours = rest_diff.total_seconds() / 3600
                        
                        # Only flag if rest hours is positive and less than 10
                        if rest_hours >= 0 and rest_hours < 10:
                            name = f"{curr_day['Firstname']} {curr_day['Lastname']}"
                            flagged.append({
                                'Name': name,
                                'Date': str(curr_day['Date']),
                                'Rest_Hours': round(rest_hours, 2),
                                'Previous_Day_Last_Out': str(prev_day_last_out),
                                'Current_Day_First_In': str(curr_day_first_in)
                            })
            except Exception as e:
                print(f"Error processing row {idx}: {e}")
                continue
        
        return flagged
    
    def flag_weekly_excess_hours(self, start_date: Optional[str] = None, end_date: Optional[str] = None) -> List[dict]:
        """Flag persons working 60 or more hours per week"""
        flagged = []
        
        # Create a working dataframe with calculated daily hours
        df_work = self.df.copy()
        df_work['InPunchTime_dt'] = pd.to_datetime(df_work['InPunchTime'])
        df_work['OutPunchTime_dt'] = pd.to_datetime(df_work['OutPunchTime'])
        
        # Calculate daily hours
        daily_hours = []
        for idx, row in df_work.iterrows():
            try:
                punch_in = row['InPunchTime_dt']
                punch_out = row['OutPunchTime_dt']
                
                if pd.notna(punch_in) and pd.notna(punch_out):
                    time_diff = punch_out - punch_in
                    
                    if time_diff.total_seconds() < 0:
                        time_diff = time_diff + timedelta(days=1)
                    
                    total_hours = time_diff.total_seconds() / 3600
                    daily_hours.append({
                        'EECode': row['EECode'],
                        'Firstname': row['Firstname'],
                        'Lastname': row['Lastname'],
                        'Date': punch_in.date(),
                        'Hours': total_hours
                    })
            except Exception:
                continue
        
        if not daily_hours:
            return flagged
        
        df_daily = pd.DataFrame(daily_hours)
        df_daily['Date'] = pd.to_datetime(df_daily['Date'])
        
        # Filter by date range if provided
        if start_date:
            start_date_dt = pd.to_datetime(start_date)
            df_daily = df_daily[df_daily['Date'] >= start_date_dt]
        if end_date:
            end_date_dt = pd.to_datetime(end_date)
            df_daily = df_daily[df_daily['Date'] <= end_date_dt]
        
        # Add week column (week starting from the earliest date or specified start_date)
        df_daily['Week'] = df_daily['Date'].dt.to_period('W')
        
        # Group by person and week
        weekly_summary = df_daily.groupby(['EECode', 'Firstname', 'Lastname', 'Week']).agg({
            'Hours': 'sum',
            'Date': ['min', 'max']
        }).reset_index()
        
        # Flatten column names
        weekly_summary.columns = ['EECode', 'Firstname', 'Lastname', 'Week', 'Total_Hours', 'Week_Start', 'Week_End']
        
        # Flag persons with weekly hours >= 60
        for idx, row in weekly_summary.iterrows():
            if row['Total_Hours'] >= 60:
                name = f"{row['Firstname']} {row['Lastname']}"
                flagged.append({
                    'Name': name,
                    'Week_Start': str(row['Week_Start']),
                    'Week_End': str(row['Week_End']),
                    'Total_Weekly_Hours': round(row['Total_Hours'], 2)
                })
        
        return flagged
    
    def flag_excess_working_days(self, start_date: Optional[str] = None, end_date: Optional[str] = None, 
                                  exclude_holidays: Optional[List[str]] = None) -> List[dict]:
        """Flag persons working more than 6 days in a week"""
        flagged = []
        
        # Create a working dataframe with calculated daily hours
        df_work = self.df.copy()
        df_work['InPunchTime_dt'] = pd.to_datetime(df_work['InPunchTime'])
        df_work['OutPunchTime_dt'] = pd.to_datetime(df_work['OutPunchTime'])
        
        # Calculate daily hours
        daily_hours = []
        for idx, row in df_work.iterrows():
            try:
                punch_in = row['InPunchTime_dt']
                punch_out = row['OutPunchTime_dt']
                
                if pd.notna(punch_in) and pd.notna(punch_out):
                    time_diff = punch_out - punch_in
                    
                    if time_diff.total_seconds() < 0:
                        time_diff = time_diff + timedelta(days=1)
                    
                    total_hours = time_diff.total_seconds() / 3600
                    if total_hours > 0:
                        daily_hours.append({
                            'EECode': row['EECode'],
                            'Firstname': row['Firstname'],
                            'Lastname': row['Lastname'],
                            'Date': punch_in.date(),
                            'Hours': total_hours
                        })
            except Exception:
                continue
        
        if not daily_hours:
            return flagged
        
        df_daily = pd.DataFrame(daily_hours)
        df_daily['Date'] = pd.to_datetime(df_daily['Date'])
        
        # Filter by date range if provided
        if start_date:
            start_date_dt = pd.to_datetime(start_date)
            df_daily = df_daily[df_daily['Date'] >= start_date_dt]
        if end_date:
            end_date_dt = pd.to_datetime(end_date)
            df_daily = df_daily[df_daily['Date'] <= end_date_dt]
        
        # Exclude holidays if provided
        if exclude_holidays:
            exclude_holidays_dt = [pd.to_datetime(h).date() for h in exclude_holidays]
            df_daily = df_daily[~df_daily['Date'].dt.date.isin(exclude_holidays_dt)]
        
        # Group by person and date to get unique working days
        df_daily_grouped = df_daily.groupby(['EECode', 'Firstname', 'Lastname', 'Date']).agg({
            'Hours': 'sum'
        }).reset_index()
        
        # Add week column to group by week
        df_daily_grouped['Week'] = df_daily_grouped['Date'].dt.to_period('W')
        
        # Count working days per person per week
        days_per_week = df_daily_grouped.groupby(['EECode', 'Firstname', 'Lastname', 'Week']).agg({
            'Date': ['count', 'min', 'max']
        }).reset_index()
        
        # Flatten column names
        days_per_week.columns = ['EECode', 'Firstname', 'Lastname', 'Week', 'Days_Worked', 'First_Day', 'Last_Day']
        
        # Flag persons with more than 6 working days in a week
        for idx, row in days_per_week.iterrows():
            if row['Days_Worked'] > 6:
                name = f"{row['Firstname']} {row['Lastname']}"
                flagged.append({
                    'Name': name,
                    'Days_Worked': int(row['Days_Worked']),
                    'Week': str(row['Week']),
                    'First_Day': str(row['First_Day']),
                    'Last_Day': str(row['Last_Day'])
                })
        
        return flagged
    
    def analyze(
        self,
        start_date: Optional[str],
        end_date: Optional[str],
        exclude_holidays: Optional[List[str]],
        report_dir: str,
        request_id: str,
    ) -> AnalysisResult:
        """
        Comprehensive payroll analysis with Excel report generation
        
        Args:
            start_date: Start date in YYYY-MM-DD format (optional)
            end_date: End date in YYYY-MM-DD format (optional)
            exclude_holidays: List of holiday dates in YYYY-MM-DD format
            report_dir: Directory to save Excel report
            request_id: Unique request identifier for logging and filename
        
        Returns:
            AnalysisResult containing flagged data, report path, and warnings
        """
        warnings: List[str] = []
        
        # Validate dates
        start_dt = self._parse_date_str(start_date, "start_date")
        end_dt = self._parse_date_str(end_date, "end_date")
        if start_dt and end_dt and start_dt > end_dt:
            raise ValueError("start_date must be earlier than or equal to end_date.")
        
        # Parse holidays
        try:
            holidays = self._parse_holidays(exclude_holidays)
        except ValueError as e:
            raise e
        
        rows_received = len(self.df)
        logger.info("[%s] rows_received=%s", request_id, rows_received)
        
        if exclude_holidays is None:
            exclude_holidays = []
        
        # Run all analysis functions (KEEPING YOUR ORIGINAL LOGIC)
        flagged_excess = self.flag_excess_hours()
        flagged_rest = self.flag_low_rest_hours()
        flagged_weekly = self.flag_weekly_excess_hours(start_date, end_date)
        flagged_days = self.flag_excess_working_days(start_date, end_date, exclude_holidays)
        
        # Calculate summary statistics
        employees = self.df['EECode'].nunique() if not self.df.empty else 0
        
        summary = {
            "rows_received": rows_received,
            "employees": int(employees),
            "flags": {
                "excess_daily_hours": len(flagged_excess),
                "low_rest_hours": len(flagged_rest),
                "weekly_excess_hours": len(flagged_weekly),
                "excess_working_days": len(flagged_days),
            }
        }
        
        # Build Excel report
        report_path = None
        try:
            os.makedirs(report_dir, exist_ok=True)
            report_path = os.path.join(report_dir, f"payroll_report_{request_id}.xlsx")
            
            with pd.ExcelWriter(report_path, engine="openpyxl") as writer:
                # Convert flagged lists to DataFrames and write to Excel
                pd.DataFrame(flagged_excess).to_excel(writer, sheet_name="Excess Daily Hours", index=False)
                pd.DataFrame(flagged_rest).to_excel(writer, sheet_name="Low Rest Hours", index=False)
                pd.DataFrame(flagged_weekly).to_excel(writer, sheet_name="Weekly Excess (>=60)", index=False)
                pd.DataFrame(flagged_days).to_excel(writer, sheet_name="Excess Days (>6)", index=False)
                pd.DataFrame([summary]).to_excel(writer, sheet_name="Summary", index=False)
            
            logger.info("[%s] report_written=%s", request_id, report_path)
        except Exception as e:
            warnings.append(f"Report generation failed: {e}")
            logger.error("[%s] report_generation_failed: %s", request_id, e)
        
        return AnalysisResult(
            data={
                "flagged_excess_hours": flagged_excess,
                "flagged_low_rest_hours": flagged_rest,
                "flagged_weekly_excess": flagged_weekly,
                "flagged_excess_days": flagged_days,
                "summary": summary,
            },
            report_path=report_path,
            warnings=warnings
        )
