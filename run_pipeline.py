"""Run the full pipeline end to end: python run_pipeline.py"""
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent / "src"
STEPS = ["generate_data.py", "etl.py", "simulate_queue.py", "load_db.py",
         "run_sql_analysis.py", "build_notebook.py", "build_excel_report.py"]

for step in STEPS:
    print(f"\n>>> {step}")
    subprocess.run([sys.executable, step], cwd=SRC, check=True)

print("\n>>> executing notebook")
subprocess.run([sys.executable, "-m", "jupyter", "nbconvert", "--to", "notebook", "--execute",
                "--inplace", "hospital_queue_eda.ipynb"], cwd=SRC.parent / "notebooks", check=True)
print("\nDone. See reports/, dashboard/ and notebooks/.")
