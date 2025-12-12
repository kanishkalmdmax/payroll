import logging
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, date
from typing import List, Optional, Tuple, Dict, Any

import pandas as pd
import csv

logger = logging.getLogger("payroll_api.service")

REQUIRED_COLUMNS = ["EECode", "Firstname", "Lastname", "InPunchTime", "OutPunchTime"]

@dataclass
class AnalysisResult:
    data: Dict[str, Any]
    report_path: Optional[str]
    warnings: List[str]

class PayrollService:
    """Service class for payroll analysis operations."""

    def __init__(self, df: pd.DataFrame):
        self.df_raw = df.copy()

    @staticmethod
    def load_file(path: str) -> pd.DataFrame:
        ext = os.path.splitext(path)[1].lower()
        if ext == ".csv":
            # Some exports wrap the *entire row* in quotes, which makes pandas
            # read the file as a single-column CSV.
            # We detect that pattern and parse it safely.
            df = pd.read_csv(path, encoding="utf-8-sig")

            # If pandas saw only one column and the header contains commas, it likely
            # means each row is quoted as one big string.
            if len(df.columns) == 1:
                col0 = str(df.columns[0])
                if "," in col0:
                    try:
                        df2 = PayrollService._read_row_wrapped_csv(path)
                        return df2
                    except Exception:
                        # Fall back to original df so we can surface a helpful error later.
                        return df

            return df
        if ext in (".xlsx", ".xlsm", ".xltx", ".xltm"):
            return pd.read_excel(path)
        # Don't support legacy .xls unless you add xlrd
        raise ValueError("Unsupported file type. Please upload a .csv or .xlsx file.")

    @staticmethod
    def _read_row_wrapped_csv(path: str) -> pd.DataFrame:
        """Parse CSV exports where each line is wrapped in quotes.

        Example problematic format:
          "EECode,Lastname,Firstname,InPunchTime,OutPunchTime,..."
          "0903,DOE,JOHN,2025-11-30 09:00,2025-11-30 18:00,..."

        After stripping the outer quotes, we can use Python's csv.reader to parse
        the inner fields (including escaped quotes like "").
        """
        rows = []
        with open(path, "r", encoding="utf-8-sig", errors="replace", newline="") as f:
            for line in f:
                line = line.rstrip("\n")
                if len(line) >= 2 and line[0] == '"' and line[-1] == '"':
                    line = line[1:-1]
                rows.append(next(csv.reader([line], delimiter=",", quotechar='"', doublequote=True)))

        if not rows or len(rows) < 2:
            raise ValueError("CSV appears empty or invalid.")

        header = [str(h).replace("\ufeff", "").strip() for h in rows[0]]
        data = rows[1:]
        df = pd.DataFrame(data, columns=header)
        return df

    @staticmethod
    def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
        # Strip BOM and whitespace from headers
        df = df.copy()
        df.columns = [str(c).replace("\ufeff", "").strip() for c in df.columns]
        return df

    @staticmethod
    def validate_headers(df: pd.DataFrame) -> None:
        cols = set(df.columns)
        missing = [c for c in REQUIRED_COLUMNS if c not in cols]
        if missing:
            raise ValueError(f"Missing required column(s): {', '.join(missing)}. "
                             f"Expected headers: {', '.join(REQUIRED_COLUMNS)}")

    @staticmethod
    def _parse_holidays(exclude_holidays: Optional[List[str]]) -> List[date]:
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
        if d is None or str(d).strip() == "":
            return None
        try:
            return pd.to_datetime(d, errors="raise")
        except Exception:
            raise ValueError(f"Invalid {field_name}: '{d}'. Use YYYY-MM-DD.")

    @staticmethod
    def _compute_shift_hours(in_dt: pd.Timestamp, out_dt: pd.Timestamp) -> float:
        if pd.isna(in_dt) or pd.isna(out_dt):
            return 0.0
        diff = out_dt - in_dt
        if diff.total_seconds() < 0:
            diff = diff + timedelta(days=1)
        return max(0.0, diff.total_seconds() / 3600.0)

    def _prepare(self) -> Tuple[pd.DataFrame, List[str]]:
        df = self._normalize_columns(self.df_raw)
        self.validate_headers(df)

        # Parse datetimes robustly
        df["InPunchTime_dt"] = pd.to_datetime(df["InPunchTime"], errors="coerce")
        df["OutPunchTime_dt"] = pd.to_datetime(df["OutPunchTime"], errors="coerce")

        warnings: List[str] = []
        bad_in = df["InPunchTime_dt"].isna().sum()
        bad_out = df["OutPunchTime_dt"].isna().sum()
        if bad_in or bad_out:
            warnings.append(
                f"{int(max(bad_in, bad_out))} row(s) had invalid In/Out datetime values and were ignored."
            )

        # Drop rows with invalid datetimes
        df = df.dropna(subset=["InPunchTime_dt", "OutPunchTime_dt"]).copy()
        if df.empty:
            raise ValueError("No valid rows found after parsing InPunchTime/OutPunchTime.")

        # Compute per-row shift hours
        df["Shift_Hours"] = df.apply(lambda r: self._compute_shift_hours(r["InPunchTime_dt"], r["OutPunchTime_dt"]), axis=1)
        df["WorkDate"] = df["InPunchTime_dt"].dt.floor("D")
        return df, warnings

    @staticmethod
    def _week_bounds(d: pd.Timestamp) -> Tuple[pd.Timestamp, pd.Timestamp]:
        # Week starts Monday
        week_start = d - pd.Timedelta(days=int(d.weekday()))
        week_start = week_start.floor("D")
        week_end = week_start + pd.Timedelta(days=6)
        return week_start, week_end

    def analyze(
        self,
        start_date: Optional[str],
        end_date: Optional[str],
        exclude_holidays: Optional[List[str]],
        report_dir: str,
        request_id: str,
    ) -> AnalysisResult:
        df, warnings = self._prepare()

        start_dt = self._parse_date_str(start_date, "start_date")
        end_dt = self._parse_date_str(end_date, "end_date")
        if start_dt and end_dt and start_dt > end_dt:
            raise ValueError("start_date must be earlier than or equal to end_date.")

        holidays = self._parse_holidays(exclude_holidays)

        rows_received = int(len(df))
        logger.info("[%s] rows_received=%s", request_id, rows_received)

        # Apply date filters (based on punch-in date)
        if start_dt is not None:
            df = df[df["WorkDate"] >= start_dt.floor("D")]
        if end_dt is not None:
            df = df[df["WorkDate"] <= end_dt.floor("D")]

        # Exclude holidays
        if holidays:
            df = df[~df["WorkDate"].dt.date.isin(holidays)]

        rows_after_filter = int(len(df))
        logger.info("[%s] rows_after_filter=%s", request_id, rows_after_filter)
        if df.empty:
            raise ValueError("No rows remain after applying date range and holiday exclusions.")

        # Aggregate to daily totals per employee
        daily = (
            df.groupby(["EECode", "Firstname", "Lastname", "WorkDate"], as_index=False)
              .agg(
                  Daily_Hours=("Shift_Hours", "sum"),
                  First_In=("InPunchTime_dt", "min"),
                  Last_Out=("OutPunchTime_dt", "max"),
              )
        )
        employees = int(daily["EECode"].nunique())

        # 1) Excess daily hours (>12)
        excess_daily = daily[daily["Daily_Hours"] > 12].copy()
        flagged_excess_hours = [
            {
                "EECode": r.EECode,
                "Firstname": r.Firstname,
                "Lastname": r.Lastname,
                "Date": str(r.WorkDate.date()),
                "Hours_Worked": round(float(r.Daily_Hours), 2),
            }
            for r in excess_daily.itertuples(index=False)
        ]

        # 2) Low rest hours between consecutive workdays (<10)
        daily_sorted = daily.sort_values(["EECode", "First_In"]).copy()
        daily_sorted["Prev_Last_Out"] = daily_sorted.groupby("EECode")["Last_Out"].shift(1)
        daily_sorted["Rest_Hours"] = (daily_sorted["First_In"] - daily_sorted["Prev_Last_Out"]).dt.total_seconds() / 3600.0

        low_rest = daily_sorted[(daily_sorted["Rest_Hours"].notna()) & (daily_sorted["Rest_Hours"] >= 0) & (daily_sorted["Rest_Hours"] < 10)].copy()
        flagged_low_rest_hours = [
            {
                "EECode": r.EECode,
                "Firstname": r.Firstname,
                "Lastname": r.Lastname,
                "Date": str(r.WorkDate.date()),
                "Rest_Hours": round(float(r.Rest_Hours), 2),
            }
            for r in low_rest.itertuples(index=False)
        ]

        # 3) Weekly excess hours (>=60)
        daily["Week_Start"] = daily["WorkDate"].apply(lambda x: self._week_bounds(x)[0])
        daily["Week_End"] = daily["WorkDate"].apply(lambda x: self._week_bounds(x)[1])

        weekly = (
            daily.groupby(["EECode", "Firstname", "Lastname", "Week_Start", "Week_End"], as_index=False)
                 .agg(Total_Hours=("Daily_Hours", "sum"), Days_Worked=("WorkDate", "nunique"))
        )

        weekly_excess = weekly[weekly["Total_Hours"] >= 60].copy()
        flagged_weekly_excess = [
            {
                "EECode": r.EECode,
                "Firstname": r.Firstname,
                "Lastname": r.Lastname,
                "Week_Start": str(pd.to_datetime(r.Week_Start).date()),
                "Week_End": str(pd.to_datetime(r.Week_End).date()),
                "Total_Hours": round(float(r.Total_Hours), 2),
            }
            for r in weekly_excess.itertuples(index=False)
        ]

        # 4) Excess working days in a week (>6)
        excess_days = weekly[weekly["Days_Worked"] > 6].copy()
        flagged_excess_days = [
            {
                "EECode": r.EECode,
                "Firstname": r.Firstname,
                "Lastname": r.Lastname,
                "Week_Start": str(pd.to_datetime(r.Week_Start).date()),
                "Week_End": str(pd.to_datetime(r.Week_End).date()),
                "Days_Worked": int(r.Days_Worked),
            }
            for r in excess_days.itertuples(index=False)
        ]

        summary = {
            "rows_received": rows_received,
            "rows_after_filter": rows_after_filter,
            "employees": employees,
            "flags": {
                "excess_daily_hours": len(flagged_excess_hours),
                "low_rest_hours": len(flagged_low_rest_hours),
                "weekly_excess_hours": len(flagged_weekly_excess),
                "excess_working_days": len(flagged_excess_days),
            }
        }

        # Build a report Excel
        report_path = None
        try:
            os.makedirs(report_dir, exist_ok=True)
            report_path = os.path.join(report_dir, f"payroll_report_{request_id}.xlsx")
            with pd.ExcelWriter(report_path, engine="openpyxl") as writer:
                pd.DataFrame(flagged_excess_hours).to_excel(writer, sheet_name="Excess Daily Hours", index=False)
                pd.DataFrame(flagged_low_rest_hours).to_excel(writer, sheet_name="Low Rest Hours", index=False)
                pd.DataFrame(flagged_weekly_excess).to_excel(writer, sheet_name="Weekly Excess (>=60)", index=False)
                pd.DataFrame(flagged_excess_days).to_excel(writer, sheet_name="Excess Days (>6)", index=False)
                pd.DataFrame([summary]).to_excel(writer, sheet_name="Summary", index=False)
            logger.info("[%s] report_written=%s", request_id, report_path)
        except Exception as e:
            warnings.append(f"Report generation failed: {e}")

        return AnalysisResult(
            data={
                "flagged_excess_hours": flagged_excess_hours,
                "flagged_low_rest_hours": flagged_low_rest_hours,
                "flagged_weekly_excess": flagged_weekly_excess,
                "flagged_excess_days": flagged_excess_days,
                "summary": summary,
            },
            report_path=report_path,
            warnings=warnings
        )
