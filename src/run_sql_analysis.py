"""Run every query in sql/analysis_queries.sql against the star schema and
export each result to reports/sql_results/<name>.csv."""
from pathlib import Path
import re
import sqlite3
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports" / "sql_results"


def load_queries():
    text = (ROOT / "sql" / "analysis_queries.sql").read_text()
    parts = re.split(r"^-- name:\s*(\S+)\s*$", text, flags=re.M)
    return dict(zip(parts[1::2], (q.strip() for q in parts[2::2])))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    pd.set_option("display.width", 160)
    with sqlite3.connect(ROOT / "data/processed/hospital_queue.db") as con:
        for name, sql in load_queries().items():
            df = pd.read_sql_query(sql, con)
            df.to_csv(OUT / f"{name}.csv", index=False)
            print(f"\n== {name} ({len(df)} rows)\n{df.head(12).to_string(index=False)}")


if __name__ == "__main__":
    main()
