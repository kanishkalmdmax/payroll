import pandas as pd
from datetime import datetime, timedelta
from typing import List, Optional


class PayrollService:
    """Service class for payroll analysis operations"""
    
    def __init__(self, excel_file_path: str):
        """Initialize the service with the Excel file path"""
        self.df = pd.read_excel(excel_file_path)
    
    def flag_excess_hours(self) -> List[dict]:
        """Flag persons with punch time exceeding 12 hours"""
        flagged = []
        
        for idx, row in self.df.iterrows():
            try:
                firstname = row['Firstname']
                lastname = row['Lastname']
                name = f"{firstname} {lastname}"
                punch_in = row['InPunchTime']
                punch_out = row['OutPunchTime']
                
                if pd.notna(punch_in) and pd.notna(punch_out):
                    t_in = pd.to_datetime(punch_in)
                    t_out = pd.to_datetime(punch_out)
                    date = t_in.date()
                    time_diff = t_out - t_in
                    
                    if time_diff.total_seconds() < 0:
                        time_diff = time_diff + timedelta(days=1)
                    
                    total_hours = time_diff.total_seconds() / 3600
                    
                    if total_hours > 12:
                        flagged.append({
                            'Name': name,
                            'Date': str(date),
                            'Total_Hours': round(total_hours, 2)
                        })
            except Exception as e:
                print(f"Error processing row {idx}: {e}")
                continue
        
        return flagged
    
    def flag_low_rest_hours(self) -> List[dict]:
        """Flag persons with rest hours less than 10"""
        flagged = []
        
        # Parse datetime columns
        df = self.df.copy()
        df['InPunchTime_dt'] = pd.to_datetime(df['InPunchTime'])
        df['OutPunchTime_dt'] = pd.to_datetime(df['OutPunchTime'])
        
        # Sort by EECode, Lastname, Firstname, and InPunchTime
        df_sorted = df.sort_values(['EECode', 'Lastname', 'Firstname', 'InPunchTime_dt']).reset_index(drop=True)
        
        for idx in range(1, len(df_sorted)):
            try:
                curr_row = df_sorted.iloc[idx]
                prev_row = df_sorted.iloc[idx - 1]
                
                # Check if same person (EECode, Lastname, Firstname)
                if (curr_row['EECode'] == prev_row['EECode'] and 
                    curr_row['Lastname'] == prev_row['Lastname'] and 
                    curr_row['Firstname'] == prev_row['Firstname']):
                    
                    curr_in = curr_row['InPunchTime_dt']
                    prev_out = prev_row['OutPunchTime_dt']
                    
                    if pd.notna(curr_in) and pd.notna(prev_out):
                        # Rest hours = current InPunchTime - previous OutPunchTime
                        rest_diff = curr_in - prev_out
                        rest_hours = rest_diff.total_seconds() / 3600
                        
                        # Only flag if rest hours is positive and less than 10
                        if rest_hours >= 0 and rest_hours < 10:
                            name = f"{curr_row['Firstname']} {curr_row['Lastname']}"
                            date = curr_in.date()
                            flagged.append({
                                'Name': name,
                                'Date': str(date),
                                'Rest_Hours': round(rest_hours, 2)
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
        
        # Count working days per person
        days_worked = df_daily_grouped.groupby(['EECode', 'Firstname', 'Lastname']).agg({
            'Date': ['count', 'min', 'max']
        }).reset_index()
        
        # Flatten column names
        days_worked.columns = ['EECode', 'Firstname', 'Lastname', 'Days_Worked', 'First_Day', 'Last_Day']
        
        # Flag persons with more than 6 working days
        for idx, row in days_worked.iterrows():
            if row['Days_Worked'] > 6:
                name = f"{row['Firstname']} {row['Lastname']}"
                flagged.append({
                    'Name': name,
                    'Days_Worked': int(row['Days_Worked']),
                    'First_Day': str(row['First_Day']),
                    'Last_Day': str(row['Last_Day'])
                })
        
        return flagged
    
    def analyze_payroll(self, start_date: str, end_date: str, exclude_holidays: Optional[List[str]] = None) -> dict:
        """
        Comprehensive payroll analysis
        
        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            exclude_holidays: List of holiday dates in YYYY-MM-DD format
        
        Returns:
            Dictionary containing all flagged entries
        """
        if exclude_holidays is None:
            exclude_holidays = []
        
        # Run all analysis functions
        flagged_excess = self.flag_excess_hours()
        flagged_rest = self.flag_low_rest_hours()
        flagged_weekly = self.flag_weekly_excess_hours(start_date, end_date)
        flagged_days = self.flag_excess_working_days(start_date, end_date, exclude_holidays)
        
        return {
            'flagged_excess_hours': flagged_excess,
            'flagged_low_rest_hours': flagged_rest,
            'flagged_weekly_excess': flagged_weekly,
            'flagged_excess_days': flagged_days
        }

