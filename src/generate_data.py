"""Generate a realistic *synthetic* OPD dataset that mirrors the Supabase schema
of the Smart Hospital Queue app (appointments, staff, users).

Real patient data cannot be published, so this script creates 90 days of
arrivals with realistic demand patterns AND realistic data-quality problems
(mixed units, typos, duplicates, missing values, inconsistent labels) for the
ETL stage to clean.

Output: data/raw/doctors.csv, data/raw/appointments_raw.csv
"""
from pathlib import Path
import numpy as np
import pandas as pd

SEED = 42
START, DAYS = "2026-01-01", 90
RAW = Path(__file__).resolve().parents[1] / "data" / "raw"

# Department mix and staffing. General Medicine is intentionally lean
# relative to demand, as is common in outpatient departments.
DEPARTMENTS = {
    #  name               share  doctors  base consult minutes
    "General Medicine": (0.42, 3, 11),
    "Pediatrics":       (0.16, 2, 10),
    "Cardiology":       (0.11, 2, 15),
    "Orthopedics":      (0.12, 2, 12),
    "Pulmonology":      (0.07, 1, 13),
    "ENT":              (0.06, 1, 9),
    "Dermatology":      (0.06, 1, 8),
}
FIRST = ["Aarav", "Meera", "Rohan", "Kavya", "Arjun", "Ananya", "Vikram",
         "Sneha", "Karthik", "Divya", "Nikhil", "Priya"]
LAST = ["Rao", "Iyer", "Reddy", "Sharma", "Nair", "Gupta", "Menon",
        "Verma", "Das", "Patel", "Joshi", "Kulkarni"]

WEEKDAY_FACTOR = [1.35, 1.10, 1.00, 1.00, 1.05, 0.85, 0.55]  # Mon..Sun
# Relative arrival intensity for 08:00..19:00 (morning rush + evening bump)
HOURLY = np.array([0.9, 1.6, 1.8, 1.4, 1.0, 0.6, 0.7, 0.8, 0.9, 1.1, 0.8, 0.4])
BASE_DAILY = 300

SYMPTOMS = {
    "General Medicine": ["fever and body ache", "headache", "cold and cough", "fatigue",
                         "high fever", "vomiting", "abdominal pain", "confusion"],
    "Pediatrics": ["fever", "cough", "rash", "high fever", "ear pain", "vomiting"],
    "Cardiology": ["chest pain", "palpitations", "shortness of breath", "dizziness",
                   "high blood pressure", "heart attack symptoms"],
    "Orthopedics": ["knee pain", "back pain", "severe pain", "fracture", "joint swelling"],
    "Pulmonology": ["shortness of breath", "breathing difficulty", "chronic cough", "wheezing"],
    "ENT": ["ear pain", "sore throat", "sinus congestion", "hearing loss"],
    "Dermatology": ["rash", "itching", "acne", "skin infection"],
}


def make_doctors(rng):
    rows, i = [], 0
    for dept, (_, n, base) in DEPARTMENTS.items():
        for _ in range(n):
            i += 1
            speed = rng.normal(1.0, 0.08)
            rows.append({
                "doctor_id": f"DOC{i:02d}",
                "name": f"Dr. {FIRST[i - 1]} {LAST[i - 1]}",
                "specialization": dept,
                "shift_hours": 8,
                "base_consult_min": round(base * speed, 1),
            })
    df = pd.DataFrame(rows)
    # One General Medicine doctor consistently runs long consultations.
    slow = df.index[df.specialization == "General Medicine"][1]
    df.loc[slow, "base_consult_min"] = 16.0
    return df


def make_appointments(rng):
    dept_names = list(DEPARTMENTS)
    shares = np.array([v[0] for v in DEPARTMENTS.values()])
    hour_p = HOURLY / HOURLY.sum()
    rows = []
    for d in pd.date_range(START, periods=DAYS):
        trend = 1 + 0.08 * (d - pd.Timestamp(START)).days / DAYS   # slight growth
        n = rng.poisson(BASE_DAILY * WEEKDAY_FACTOR[d.weekday()] * trend)
        hours = rng.choice(np.arange(8, 20), size=n, p=hour_p)
        mins = rng.uniform(0, 60, size=n)
        depts = rng.choice(dept_names, size=n, p=shares)
        for h, m, dept in zip(hours, mins, depts):
            if dept == "Pediatrics":
                age = int(rng.integers(0, 15))
            elif dept == "Cardiology":
                age = int(np.clip(rng.normal(60, 12), 25, 95))
            else:
                age = int(np.clip(rng.normal(40, 18), 15, 95))
            fever = round(float(np.clip(rng.normal(37.4, 0.8), 36, 41.5)), 1)
            if "fever" in (sym := str(rng.choice(SYMPTOMS[dept]))):
                fever = round(float(np.clip(rng.normal(38.9, 0.6), 37.5, 41.5)), 1)
            sbp = int(np.clip(rng.normal(125 + 0.4 * max(age - 40, 0), 17), 75, 210))
            dbp = int(np.clip(sbp * rng.normal(0.65, 0.04), 45, 130))
            spo2 = int(np.clip(rng.normal(97.3, 1.6), 85, 100))
            if dept == "Pulmonology" or "breath" in sym:
                spo2 = int(np.clip(rng.normal(93.5, 2.5), 84, 100))
            rows.append({
                "created_at": d + pd.Timedelta(hours=int(h), minutes=float(m)),
                "patient_id": f"P{rng.integers(1, 9000):05d}",
                "gender": rng.choice(["M", "F"]),
                "age": age,
                "department": dept,
                "symptoms": sym,
                "fever": fever,
                "blood_pressure_systolic": sbp,
                "blood_pressure_diastolic": dbp,
                "spo2": spo2,
                "pre_cancelled": rng.random() < 0.03,
            })
    df = pd.DataFrame(rows).sort_values("created_at").reset_index(drop=True)
    return inject_quality_issues(df, rng)


def inject_quality_issues(df, rng):
    n = len(df)
    pick = lambda frac: rng.choice(n, size=int(n * frac), replace=False)
    df["fever"] = df["fever"].astype(object)
    df["spo2"] = df["spo2"].astype(object)
    df["age"] = df["age"].astype(object)
    # Fever entered in Fahrenheit by some front-desk staff
    idx = pick(0.02); df.loc[idx, "fever"] = (df.loc[idx, "fever"].astype(float) * 9 / 5 + 32).round(1)
    # Missing vitals
    df.loc[pick(0.015), "spo2"] = np.nan
    df.loc[pick(0.01), "fever"] = np.nan
    # Impossible values from typos
    df.loc[pick(0.003), "spo2"] = rng.choice([0, 970, 199])
    df.loc[pick(0.002), "age"] = rng.choice([-1, 250])
    # Inconsistent department labels
    idx = pick(0.05)
    df.loc[idx, "department"] = df.loc[idx, "department"].map(
        lambda s: rng.choice([s.upper(), s.lower(), f" {s} ", s.replace(" ", "")]))
    # Double-submitted bookings
    dup = df.loc[pick(0.006)]
    df = pd.concat([df, dup]).sort_values("created_at").reset_index(drop=True)
    df.insert(0, "appointment_id", [f"A{i:06d}" for i in range(1, len(df) + 1)])
    return df


def main():
    rng = np.random.default_rng(SEED)
    RAW.mkdir(parents=True, exist_ok=True)
    doctors = make_doctors(rng)
    appts = make_appointments(rng)
    doctors.to_csv(RAW / "doctors.csv", index=False)
    appts.to_csv(RAW / "appointments_raw.csv", index=False)
    print(f"doctors: {len(doctors)} rows | appointments_raw: {len(appts):,} rows")


if __name__ == "__main__":
    main()
