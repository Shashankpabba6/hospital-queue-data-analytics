"""Extract -> Transform -> validate raw appointment data.

Every cleaning rule logs how many rows it touched so the data-quality
report (reports/data_quality_log.csv) can be audited.
Output: data/processed/appointments_clean.csv
"""
from pathlib import Path
import numpy as np
import pandas as pd
from severity import predict_severity

ROOT = Path(__file__).resolve().parents[1]
RAW, PROC, REPORTS = ROOT / "data/raw", ROOT / "data/processed", ROOT / "reports"
VALID_DEPTS = ["General Medicine", "Pediatrics", "Cardiology", "Orthopedics",
               "Pulmonology", "ENT", "Dermatology"]

log = []


def record(step, rows_affected, note=""):
    log.append({"step": step, "rows_affected": int(rows_affected), "note": note})
    print(f"  {step:<38} {rows_affected:>6,}  {note}")


def transform(df):
    record("extract: raw rows", len(df))

    key_cols = [c for c in df.columns if c != "appointment_id"]
    dups = df.duplicated(subset=key_cols, keep="first")
    df = df[~dups].copy()
    record("remove duplicate submissions", dups.sum())

    norm = {d.replace(" ", "").lower(): d for d in VALID_DEPTS}
    cleaned = df["department"].str.strip().str.replace(" ", "").str.lower().map(norm)
    record("standardise department labels", (cleaned != df["department"]).sum())
    df["department"] = cleaned
    record("unmapped departments (dropped)", df["department"].isna().sum())
    df = df.dropna(subset=["department"])

    df["fever"] = pd.to_numeric(df["fever"], errors="coerce")
    f_mask = df["fever"] > 45
    df.loc[f_mask, "fever"] = ((df.loc[f_mask, "fever"] - 32) * 5 / 9).round(1)
    record("convert fever F -> C", f_mask.sum(), "values > 45 treated as Fahrenheit")

    df["spo2"] = pd.to_numeric(df["spo2"], errors="coerce")
    bad = (df["spo2"] < 50) | (df["spo2"] > 100)
    df.loc[bad, "spo2"] = np.nan
    record("invalid SpO2 -> null", bad.sum(), "outside 50-100%")

    df["age"] = pd.to_numeric(df["age"], errors="coerce")
    bad = (df["age"] < 0) | (df["age"] > 110)
    df.loc[bad, "age"] = np.nan
    record("invalid age -> null", bad.sum(), "outside 0-110")

    # Impute with department medians and flag, so triage still runs
    for col in ["fever", "spo2", "age"]:
        miss = df[col].isna()
        df[f"{col}_imputed"] = miss
        df[col] = df[col].fillna(df.groupby("department")[col].transform("median"))
        record(f"impute missing {col} (dept median)", miss.sum())

    df["created_at"] = pd.to_datetime(df["created_at"])
    df["severity_score"] = [
        predict_severity(f, s, o, a, sym) for f, s, o, a, sym in
        zip(df.fever, df.blood_pressure_systolic, df.spo2, df.age, df.symptoms)
    ]
    df["age"] = df["age"].round().astype(int)
    return df.reset_index(drop=True)


def validate(df):
    checks = {
        "appointment_id unique": df["appointment_id"].is_unique,
        "no nulls in vitals": df[["fever", "spo2", "age",
                                  "blood_pressure_systolic"]].notna().all().all(),
        "fever within 34-43 C": df["fever"].between(34, 43).all(),
        "spo2 within 50-100": df["spo2"].between(50, 100).all(),
        "severity within 1-5": df["severity_score"].between(1, 5).all(),
        "departments valid": df["department"].isin(VALID_DEPTS).all(),
    }
    for name, ok in checks.items():
        record(f"validate: {name}", 0, "PASS" if ok else "FAIL")
        assert ok, f"Validation failed: {name}"


def main():
    print("ETL - appointments")
    df = pd.read_csv(RAW / "appointments_raw.csv")
    df = transform(df)
    validate(df)
    record("load: clean rows", len(df))
    PROC.mkdir(parents=True, exist_ok=True)
    df.to_csv(PROC / "appointments_clean.csv", index=False)
    pd.DataFrame(log).to_csv(REPORTS / "data_quality_log.csv", index=False)


if __name__ == "__main__":
    main()
