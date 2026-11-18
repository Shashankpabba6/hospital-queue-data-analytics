"""Build docs/index.html: an interactive, self-contained web version of the
3-page Power BI dashboard (served by GitHub Pages from /docs).

The page computes the same KPIs as dashboard/powerbi_measures.dax from the
embedded fact table, so slicers (department, date range) update every visual.
"""
from pathlib import Path
import json
import sqlite3
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "src" / "web_dashboard_template.html"
OUT = ROOT / "docs" / "index.html"
STATUS = {"completed": 0, "no_show": 1, "cancelled": 2}


def main():
    con = sqlite3.connect(ROOT / "data/processed/hospital_queue.db")
    f = pd.read_sql_query("SELECT * FROM fact_appointment ORDER BY created_at", con)
    dates = pd.read_sql_query("SELECT date_key, full_date, day_of_week FROM dim_date ORDER BY date_key", con)
    depts = pd.read_sql_query("SELECT * FROM dim_department ORDER BY department_id", con)
    docs = pd.read_sql_query("SELECT * FROM dim_doctor ORDER BY doctor_id", con)

    day_idx = {k: i for i, k in enumerate(dates.date_key)}
    doc_idx = {k: i for i, k in enumerate(docs.doctor_id)}
    to10 = lambda s: [int(round(v * 10)) if pd.notna(v) else -1 for v in s]
    data = {
        "dates": dates.full_date.tolist(),
        "weekday": (dates.day_of_week - 1).tolist(),          # 0 = Monday
        "depts": depts.department_name.tolist(),
        "doctors": [{"name": r.name, "dept": int(r.department_id) - 1, "shift": int(r.shift_hours)}
                    for r in docs.itertuples()],
        "d": f.date_key.map(day_idx).tolist(),
        "p": (f.department_id - 1).tolist(),
        "h": f.arrival_hour.tolist(),
        "s": f.severity_score.tolist(),
        "st": f.status.map(STATUS).tolist(),
        "w": to10(f.waiting_time_min),
        "c": to10(f.consult_duration_min),
        "o": [doc_idx.get(x, -1) if x else -1 for x in f.doctor_id],
    }
    OUT.parent.mkdir(exist_ok=True)
    html = TEMPLATE.read_text().replace("__DATA__", json.dumps(data, separators=(",", ":")))
    OUT.write_text(html)
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size / 1024:.0f} KB, {len(f):,} rows)")


if __name__ == "__main__":
    main()
