"""Load processed data into a star schema (SQLite file for portability;
sql/schema_mysql.sql has the equivalent MySQL DDL).

  dim_doctor, dim_date, dim_department  <-  fact_appointment
"""
from pathlib import Path
import sqlite3
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROC, RAW = ROOT / "data/processed", ROOT / "data/raw"
DB = PROC / "hospital_queue.db"


def main():
    a = pd.read_csv(PROC / "appointments.csv", parse_dates=["created_at"])
    doctors = pd.read_csv(RAW / "doctors.csv")

    depts = sorted(a.department.unique())
    dim_department = pd.DataFrame({"department_id": range(1, len(depts) + 1),
                                   "department_name": depts})
    dept_id = dict(zip(dim_department.department_name, dim_department.department_id))

    dim_doctor = doctors.assign(department_id=doctors.specialization.map(dept_id))[
        ["doctor_id", "name", "department_id", "shift_hours", "base_consult_min"]]

    dates = pd.date_range(a.created_at.min().normalize(), a.created_at.max().normalize())
    dim_date = pd.DataFrame({
        "date_key": dates.strftime("%Y%m%d").astype(int),
        "full_date": dates.strftime("%Y-%m-%d"),
        "day_name": dates.day_name(),
        "day_of_week": dates.day_of_week + 1,
        "week_of_year": dates.isocalendar().week.values,
        "month_name": dates.month_name(),
        "is_weekend": (dates.day_of_week >= 5).astype(int),
    })

    fact = pd.DataFrame({
        "appointment_id": a.appointment_id,
        "date_key": a.created_at.dt.strftime("%Y%m%d").astype(int),
        "arrival_hour": a.created_at.dt.hour,
        "created_at": a.created_at.dt.strftime("%Y-%m-%d %H:%M:%S"),
        "patient_id": a.patient_id,
        "department_id": a.department.map(dept_id),
        "doctor_id": a.doctor_id,
        "token_number": a.token_number,
        "age": a.age,
        "gender": a.gender,
        "severity_score": a.severity_score,
        "fever": a.fever,
        "spo2": a.spo2,
        "bp_systolic": a.blood_pressure_systolic,
        "status": a.status,
        "waiting_time_min": a.waiting_time_min,
        "consult_duration_min": a.consult_duration_min,
    })

    DB.unlink(missing_ok=True)
    with sqlite3.connect(DB) as con:
        for name, df in [("dim_department", dim_department), ("dim_doctor", dim_doctor),
                         ("dim_date", dim_date), ("fact_appointment", fact)]:
            df.to_sql(name, con, index=False)
            print(f"  loaded {name:<17} {len(df):>7,} rows")
        comp = pd.read_csv(PROC / "policy_comparison.csv")
        comp[["appointment_id", "department", "severity_score", "wait_fifo", "status_fifo",
              "wait_priority", "status_priority"]].to_sql("sim_policy_comparison", con, index=False)
        print(f"  loaded {'sim_policy_comparison':<17} {len(comp):>7,} rows")
        con.execute("CREATE INDEX ix_fact_date ON fact_appointment(date_key)")
        con.execute("CREATE INDEX ix_fact_doc ON fact_appointment(doctor_id)")
        # Row-count reconciliation: source vs loaded
        loaded = con.execute("SELECT COUNT(*) FROM fact_appointment").fetchone()[0]
        assert loaded == len(a), "row count mismatch between CSV and fact table"
        print(f"  row-count check PASS ({loaded:,} = {len(a):,})")

    # Flat CSV extracts for Power BI / Excel
    for name, df in [("dim_department", dim_department), ("dim_doctor", dim_doctor),
                     ("dim_date", dim_date), ("fact_appointment", fact)]:
        df.to_csv(ROOT / "dashboard" / "powerbi_data" / f"{name}.csv", index=False)


if __name__ == "__main__":
    (ROOT / "dashboard" / "powerbi_data").mkdir(parents=True, exist_ok=True)
    main()
