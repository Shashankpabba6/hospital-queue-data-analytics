"""Discrete-event simulation of each department's OPD queue.

The SAME arrivals, consultation times and patience are replayed under two
policies so the comparison is apples-to-apples:
  * fifo     - first come, first served (pre-system baseline)
  * priority - the app's rule: ORDER BY severity_score DESC, queue_position ASC

Patients whose wait exceeds their patience leave (status = no_show).
Output: data/processed/appointments.csv (priority policy = the live system)
        data/processed/policy_comparison.csv (per-patient wait under both)
"""
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROC, RAW = ROOT / "data/processed", ROOT / "data/raw"
SHIFT_START_MIN = 8 * 60
# Mean patience (minutes) before a waiting patient walks out, by severity
PATIENCE_MEAN = {1: 120, 2: 140, 3: 200, 4: 600, 5: 10_000}


def simulate_day(patients, doctors, policy):
    """patients: list of dicts with arr, sev, work, patience. Returns results.
    Doctors may carry start_min / end_min (stop taking new patients) for
    part-time scenarios; regular doctors stay until the queue is cleared."""
    free = {d["doctor_id"]: d.get("start_min", SHIFT_START_MIN) for d in doctors}
    end = {d["doctor_id"]: d.get("end_min", float("inf")) for d in doctors}
    base = {d["doctor_id"]: d["base_consult_min"] for d in doctors}
    pending = sorted(patients, key=lambda p: p["arr"])
    out = []
    while pending:
        doc = min((d for d in free if free[d] < end[d]), key=free.get)
        t = free[doc]
        still = []
        for p in pending:            # walk-outs: waited longer than patience
            if p["arr"] + p["patience"] < t:
                out.append({**p, "status": "no_show", "doctor_id": None,
                            "start": None, "end": None,
                            "wait": p["patience"]})
            else:
                still.append(p)
        pending = still
        if not pending:
            break
        waiting = [p for p in pending if p["arr"] <= t]
        if not waiting:
            free[doc] = min(p["arr"] for p in pending)
            continue
        if policy == "priority":
            nxt = min(waiting, key=lambda p: (-p["sev"], p["arr"]))
        else:
            nxt = min(waiting, key=lambda p: p["arr"])
        service = base[doc] * nxt["work"] * (1 + 0.12 * (nxt["sev"] - 1))
        out.append({**nxt, "status": "completed", "doctor_id": doc,
                    "start": t, "end": t + service, "wait": t - nxt["arr"]})
        free[doc] = t + service
        pending.remove(nxt)
    return out


def main():
    rng = np.random.default_rng(7)
    appts = pd.read_csv(PROC / "appointments_clean.csv", parse_dates=["created_at"])
    doctors = pd.read_csv(RAW / "doctors.csv")

    appts["arr"] = appts.created_at.dt.hour * 60 + appts.created_at.dt.minute \
        + appts.created_at.dt.second / 60
    appts["work"] = rng.lognormal(0, 0.35, len(appts))
    appts["patience"] = [rng.exponential(PATIENCE_MEAN[s]) + 5 for s in appts.severity_score]
    appts["date"] = appts.created_at.dt.date

    # What-if: one extra General Medicine doctor covering the 09:00-13:00 rush
    gm = doctors[doctors.specialization == "General Medicine"]
    extra = {"doctor_id": "DOC_EXTRA", "base_consult_min": round(gm.base_consult_min.median(), 1),
             "start_min": 9 * 60, "end_min": 13 * 60}

    results = {"fifo": [], "priority": [], "priority_plus_gm_doctor": []}
    active = appts[~appts.pre_cancelled]
    for (date, dept), grp in active.groupby(["date", "department"]):
        docs = doctors[doctors.specialization == dept].to_dict("records")
        pts = [{"appointment_id": r.appointment_id, "arr": r.arr, "sev": r.severity_score,
                "work": r.work, "patience": r.patience}
               for r in grp.itertuples()]
        results["fifo"] += simulate_day(pts, docs, "fifo")
        results["priority"] += simulate_day(pts, docs, "priority")
        scen_docs = docs + [extra] if dept == "General Medicine" else docs
        results["priority_plus_gm_doctor"] += simulate_day(pts, scen_docs, "priority")

    sim = {k: pd.DataFrame(v).set_index("appointment_id") for k, v in results.items()}
    comp = sim["fifo"][["wait", "status"]].add_suffix("_fifo").join(
        sim["priority"][["wait", "status"]].add_suffix("_priority"))
    comp = comp.join(appts.set_index("appointment_id")[["department", "severity_score", "created_at"]])
    comp.round({"wait_fifo": 2, "wait_priority": 2}).to_csv(PROC / "policy_comparison.csv")

    dept = appts.set_index("appointment_id").department
    rows = []
    for name, df in sim.items():
        df = df.join(dept)
        for d, g in [("All departments", df), ("General Medicine", df[df.department == "General Medicine"])]:
            rows.append({"scenario": name, "scope": d,
                         "avg_wait_min": round(g.wait.mean(), 1),
                         "pct_wait_over_30": round(100 * (g.wait > 30).mean(), 1),
                         "no_show_pct": round(100 * (g.status == "no_show").mean(), 1)})
    pd.DataFrame(rows).to_csv(PROC / "scenario_results.csv", index=False)
    print(pd.DataFrame(rows).to_string(index=False))

    live = sim["priority"]
    day0 = appts.set_index("appointment_id").created_at.dt.normalize()
    out = appts.set_index("appointment_id").drop(columns=["arr", "work", "patience", "date"])
    out = out.join(live[["doctor_id", "status", "wait", "start", "end"]])
    out["status"] = out["status"].fillna("cancelled")
    out["waiting_time_min"] = out["wait"].round(1)
    out.loc[out.status == "cancelled", "waiting_time_min"] = np.nan
    out["consult_start"] = day0 + pd.to_timedelta(out["start"], unit="m")
    out["consult_end"] = day0 + pd.to_timedelta(out["end"], unit="m")
    out["consult_duration_min"] = (out["end"] - out["start"]).round(1)
    out = out.drop(columns=["wait", "start", "end"])
    # Token numbers restart daily per department, like the app
    out = out.sort_values("created_at")
    out["token_number"] = out.groupby([out.created_at.dt.date, "department"]).cumcount() + 1
    out.reset_index().to_csv(PROC / "appointments.csv", index=False)

    served = comp[(comp.status_fifo == "completed") | (comp.status_priority == "completed")]
    print(f"simulated {len(comp):,} visits | mean wait FIFO {served.wait_fifo.mean():.1f} min "
          f"| priority {served.wait_priority.mean():.1f} min")


if __name__ == "__main__":
    main()
