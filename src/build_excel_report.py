"""Build dashboard/Hospital_Queue_KPI_Report.xlsx: KPI summary, pivot summaries
and native Excel charts, ready to hand to hospital management."""
from pathlib import Path
import sqlite3
import pandas as pd
from openpyxl import load_workbook
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.formatting.rule import ColorScaleRule
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parents[1]
SQL_OUT = ROOT / "reports" / "sql_results"
OUT = ROOT / "dashboard" / "Hospital_Queue_KPI_Report.xlsx"
HEADER = PatternFill("solid", fgColor="2A78D6")


def style_sheet(ws):
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = HEADER
        cell.alignment = Alignment(horizontal="center", wrap_text=True)
    for i, col in enumerate(ws.columns, 1):
        width = max(len(str(c.value)) if c.value is not None else 0 for c in col)
        ws.column_dimensions[get_column_letter(i)].width = min(max(10, width + 2), 32)
    ws.freeze_panes = "A2"


def bar_chart(ws, title, cats_col, val_col, n, anchor, y_title):
    ch = BarChart(); ch.type = "bar" if n > 8 else "col"
    ch.title, ch.y_axis.title, ch.legend = title, y_title, None
    ch.add_data(Reference(ws, min_col=val_col, min_row=1, max_row=n + 1), titles_from_data=True)
    ch.set_categories(Reference(ws, min_col=cats_col, min_row=2, max_row=n + 1))
    ch.series[0].graphicalProperties.solidFill = "2A78D6"
    ch.height, ch.width = 8, 16
    ws.add_chart(ch, anchor)


def main():
    con = sqlite3.connect(ROOT / "data/processed/hospital_queue.db")
    fact = pd.read_sql_query("""
        SELECT f.appointment_id, dt.full_date, dt.day_name, f.arrival_hour, d.department_name,
               f.doctor_id, f.severity_score, f.status, f.waiting_time_min, f.consult_duration_min
        FROM fact_appointment f
        JOIN dim_date dt ON dt.date_key = f.date_key
        JOIN dim_department d ON d.department_id = f.department_id""", con)
    kpi = pd.read_csv(SQL_OUT / "01_kpi_overview.csv").T.reset_index()
    kpi.columns = ["KPI", "Value"]
    kpi["KPI"] = kpi["KPI"].str.replace("_", " ").str.title()

    served = fact[fact.status == "completed"]
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    pivot_wait = served.pivot_table(index="day_name", columns="arrival_hour",
                                    values="waiting_time_min", aggfunc="mean").reindex(days).round(1)
    pivot_dept = fact.pivot_table(index="department_name", columns="status",
                                  values="appointment_id", aggfunc="count", fill_value=0)
    pivot_dept["no_show_rate_%"] = (100 * pivot_dept["no_show"] /
                                    (pivot_dept["completed"] + pivot_dept["no_show"])).round(1)

    sheets = {
        "KPI Summary": kpi,
        "Department": pd.read_csv(SQL_OUT / "02_department_bottlenecks.csv"),
        "Hourly Load": pd.read_csv(SQL_OUT / "03_hourly_load.csv"),
        "Pivot Wait DayxHour": pivot_wait.reset_index(),
        "Pivot Dept Status": pivot_dept.reset_index(),
        "Doctor Workload": pd.read_csv(SQL_OUT / "06_doctor_workload.csv"),
        "Daily Trend": pd.read_csv(SQL_OUT / "08_daily_trend.csv"),
        "Policy Impact": pd.read_csv(SQL_OUT / "10_policy_impact_by_severity.csv").astype({"severity_score": object})
                           .fillna({"severity_score": "All"}),
        "Data": fact,
    }
    with pd.ExcelWriter(OUT, engine="openpyxl") as xw:
        for name, df in sheets.items():
            df.to_excel(xw, sheet_name=name, index=False)

    wb = load_workbook(OUT)
    for ws in wb.worksheets:
        style_sheet(ws)
    bar_chart(wb["Department"], "Avg waiting time by department", 1, 5, 7, "J2", "Minutes")
    bar_chart(wb["Hourly Load"], "Average arrivals per day by hour", 1, 3, 12, "G2", "Patients")
    bar_chart(wb["Doctor Workload"], "Staff Fatigue Index (%)", 1, 5, 12, "I2", "% of shift")
    ws = wb["Daily Trend"]
    lc = LineChart(); lc.title, lc.y_axis.title, lc.height, lc.width = "Daily visits & 7-day average", "Visits", 8, 22
    lc.add_data(Reference(ws, min_col=2, max_col=3, min_row=1, max_row=ws.max_row), titles_from_data=True)
    lc.set_categories(Reference(ws, min_col=1, min_row=2, max_row=ws.max_row))
    ws.add_chart(lc, "G2")
    ws = wb["Pivot Wait DayxHour"]
    ws.conditional_formatting.add(f"B2:{get_column_letter(ws.max_column)}8",
                                  ColorScaleRule(start_type="min", start_color="FFFFFF",
                                                 end_type="max", end_color="2A78D6"))
    wb["Data"].auto_filter.ref = wb["Data"].dimensions
    wb.save(OUT)
    print(f"wrote {OUT.name} ({len(wb.sheetnames)} sheets)")


if __name__ == "__main__":
    main()
