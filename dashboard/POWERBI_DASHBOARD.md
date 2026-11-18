# Power BI dashboard build guide

The data model and every measure are ready; the `.pbix` is built in Power BI Desktop
(Windows) in ~30 minutes. Add screenshots to `reports/figures/powerbi_*.png` when done.

## 1. Load
`Get Data > Text/CSV` → load the 4 files in `dashboard/powerbi_data/`.
Power Query steps: set `full_date` to Date, `created_at` to Date/Time, `waiting_time_min`
to Decimal; mark `dim_date` as a date table on `full_date`.

## 2. Model (star schema)
```
dim_date[date_key]            1 ──* fact_appointment[date_key]
dim_department[department_id] 1 ──* fact_appointment[department_id]
dim_doctor[doctor_id]         1 ──* fact_appointment[doctor_id]
```

## 3. Measures
Paste from `powerbi_measures.dax`.

## 4. Pages

| Page | Visuals (6 KPI visuals on page 1) |
|------|-------------------------------------|
| **1. Operations overview** | KPI cards: Total Bookings, Avg Wait, P90 Wait, % Waits Over 30 min, No Show Rate %, Critical Patients · Line: Visits + Visits 7D MA by date · Slicers: department, date range |
| **2. Bottlenecks** | Matrix heatmap: day_name × arrival_hour → Avg Wait (conditional formatting) · Bar: Avg Wait by department · Column: arrivals by hour |
| **3. Doctor workload** | Bar: Fatigue Index % by doctor (reference line at 100%) · Table: doctor, patients/day, Avg Consult · Scatter: Avg Consult vs Patients per Day |
