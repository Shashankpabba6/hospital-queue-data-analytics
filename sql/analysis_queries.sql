-- Hospital Queue Analytics: analysis queries
-- Portable ANSI SQL (runs on MySQL 8+, PostgreSQL and SQLite 3.25+).
-- Each block starts with "-- name:" so src/run_sql_analysis.py can execute
-- and export them individually.

-- name: 01_kpi_overview
-- Headline KPIs for the whole 90-day period
SELECT
    COUNT(*)                                                        AS total_bookings,
    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END)           AS completed_visits,
    ROUND(100.0 * SUM(CASE WHEN status = 'no_show' THEN 1 ELSE 0 END)
          / SUM(CASE WHEN status <> 'cancelled' THEN 1 ELSE 0 END), 2) AS no_show_rate_pct,
    ROUND(AVG(CASE WHEN status = 'completed' THEN waiting_time_min END), 1) AS avg_wait_min,
    ROUND(100.0 * SUM(CASE WHEN status = 'completed' AND waiting_time_min > 30 THEN 1 ELSE 0 END)
          / SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END), 2) AS pct_waits_over_30min,
    ROUND(AVG(consult_duration_min), 1)                             AS avg_consult_min
FROM fact_appointment;

-- name: 02_department_bottlenecks
-- Demand per doctor vs. waiting time; ranked to surface the worst department
WITH dept_daily AS (
    SELECT f.department_id, f.date_key, COUNT(*) AS visits
    FROM fact_appointment f
    WHERE f.status <> 'cancelled'
    GROUP BY f.department_id, f.date_key
),
doc_count AS (
    SELECT department_id, COUNT(*) AS doctors FROM dim_doctor GROUP BY department_id
),
dept_wait AS (
    SELECT department_id,
           AVG(waiting_time_min) AS avg_wait,
           AVG(CASE WHEN waiting_time_min > 30 THEN 1.0 ELSE 0 END) AS share_over_30,
           AVG(CASE WHEN status = 'no_show' THEN 1.0 ELSE 0 END) AS no_show_rate
    FROM fact_appointment
    WHERE status <> 'cancelled'
    GROUP BY department_id
)
SELECT d.department_name,
       c.doctors,
       ROUND(AVG(dd.visits), 1)                         AS avg_daily_visits,
       ROUND(AVG(dd.visits) * 1.0 / c.doctors, 1)       AS visits_per_doctor_day,
       ROUND(w.avg_wait, 1)                             AS avg_wait_min,
       ROUND(100 * w.share_over_30, 1)                  AS pct_over_30min,
       ROUND(100 * w.no_show_rate, 1)                   AS no_show_pct,
       RANK() OVER (ORDER BY w.avg_wait DESC)           AS wait_rank
FROM dept_daily dd
JOIN dim_department d ON d.department_id = dd.department_id
JOIN doc_count c      ON c.department_id = dd.department_id
JOIN dept_wait w      ON w.department_id = dd.department_id
GROUP BY d.department_name, c.doctors, w.avg_wait, w.share_over_30, w.no_show_rate
ORDER BY wait_rank;

-- name: 03_hourly_load
-- Arrival volume and waiting time by hour of day (peak-hour detection)
SELECT arrival_hour,
       COUNT(*)                                   AS arrivals,
       ROUND(COUNT(*) * 1.0 / (SELECT COUNT(*) FROM dim_date), 1) AS avg_arrivals_per_day,
       ROUND(AVG(waiting_time_min), 1)            AS avg_wait_min,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS share_of_daily_pct
FROM fact_appointment
WHERE status <> 'cancelled'
GROUP BY arrival_hour
ORDER BY arrival_hour;

-- name: 04_weekday_pattern
WITH daily AS (
    SELECT dt.day_of_week, dt.day_name, f.date_key,
           COUNT(*) AS visits, AVG(f.waiting_time_min) AS avg_wait
    FROM fact_appointment f
    JOIN dim_date dt ON dt.date_key = f.date_key
    WHERE f.status <> 'cancelled'
    GROUP BY dt.day_of_week, dt.day_name, f.date_key
)
SELECT day_name,
       ROUND(AVG(visits), 0)   AS avg_daily_visits,
       ROUND(AVG(avg_wait), 1) AS avg_wait_min,
       ROUND(100.0 * (AVG(visits) - (SELECT AVG(visits) FROM daily)) / (SELECT AVG(visits) FROM daily), 1)
                               AS pct_vs_avg_day
FROM daily
GROUP BY day_of_week, day_name
ORDER BY day_of_week;

-- name: 05_peak_slots
-- Top 10 weekday x hour slots by waiting time
WITH slot AS (
    SELECT dt.day_name, f.arrival_hour,
           COUNT(*) AS visits, AVG(f.waiting_time_min) AS avg_wait
    FROM fact_appointment f
    JOIN dim_date dt ON dt.date_key = f.date_key
    WHERE f.status = 'completed'
    GROUP BY dt.day_name, f.arrival_hour
)
SELECT * FROM (
    SELECT day_name, arrival_hour, visits, ROUND(avg_wait, 1) AS avg_wait_min,
           DENSE_RANK() OVER (ORDER BY avg_wait DESC) AS slot_rank
    FROM slot
) ranked
WHERE slot_rank <= 10
ORDER BY slot_rank;

-- name: 06_doctor_workload
-- Workload, consultation length and fatigue index; compared with dept peers
WITH doc AS (
    SELECT f.doctor_id,
           COUNT(*) * 1.0 / COUNT(DISTINCT f.date_key) AS patients_per_day,
           AVG(f.consult_duration_min)                 AS avg_consult,
           AVG(f.waiting_time_min)                     AS avg_wait_of_patients
    FROM fact_appointment f
    WHERE f.status = 'completed'
    GROUP BY f.doctor_id
)
SELECT dd.name, dp.department_name,
       ROUND(doc.patients_per_day, 1) AS patients_per_day,
       ROUND(doc.avg_consult, 1)      AS avg_consult_min,
       -- Staff Fatigue Index from the app: consulting minutes / shift minutes
       ROUND(100 * doc.patients_per_day * doc.avg_consult / (dd.shift_hours * 60), 0) AS fatigue_pct,
       ROUND(doc.avg_consult - AVG(doc.avg_consult) OVER (PARTITION BY dd.department_id), 1)
                                      AS consult_min_vs_dept_avg,
       RANK() OVER (PARTITION BY dd.department_id ORDER BY doc.avg_consult DESC) AS slowest_in_dept
FROM doc
JOIN dim_doctor dd     ON dd.doctor_id = doc.doctor_id
JOIN dim_department dp ON dp.department_id = dd.department_id
ORDER BY fatigue_pct DESC;

-- name: 07_severity_mix_and_wait
SELECT severity_score,
       COUNT(*)                                    AS visits,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS share_pct,
       ROUND(AVG(waiting_time_min), 1)             AS avg_wait_min,
       ROUND(100.0 * AVG(CASE WHEN status = 'no_show' THEN 1.0 ELSE 0 END), 1) AS no_show_pct
FROM fact_appointment
WHERE status <> 'cancelled'
GROUP BY severity_score
ORDER BY severity_score;

-- name: 08_daily_trend
-- Daily volume with 7-day moving average and week-over-week change (LAG)
WITH daily AS (
    SELECT f.date_key, dt.full_date, COUNT(*) AS visits,
           AVG(f.waiting_time_min) AS avg_wait
    FROM fact_appointment f
    JOIN dim_date dt ON dt.date_key = f.date_key
    WHERE f.status <> 'cancelled'
    GROUP BY f.date_key, dt.full_date
)
SELECT full_date, visits,
       ROUND(AVG(visits) OVER (ORDER BY date_key ROWS BETWEEN 6 PRECEDING AND CURRENT ROW), 1) AS visits_7d_ma,
       ROUND(avg_wait, 1) AS avg_wait_min,
       visits - LAG(visits, 7) OVER (ORDER BY date_key) AS wow_change
FROM daily
ORDER BY date_key;

-- name: 09_no_show_by_wait_band
-- Do long waits drive walk-outs?
SELECT CASE
         WHEN waiting_time_min < 15  THEN '1) < 15 min'
         WHEN waiting_time_min < 30  THEN '2) 15-30 min'
         WHEN waiting_time_min < 60  THEN '3) 30-60 min'
         WHEN waiting_time_min < 120 THEN '4) 60-120 min'
         ELSE '5) 120+ min' END                  AS wait_band,
       COUNT(*)                                  AS patients,
       ROUND(100.0 * AVG(CASE WHEN status = 'no_show' THEN 1.0 ELSE 0 END), 1) AS no_show_pct
FROM fact_appointment
WHERE status IN ('completed', 'no_show')
GROUP BY 1
ORDER BY 1;

-- name: 10_policy_impact_by_severity
-- FIFO baseline vs the app's severity-priority queue (same simulated arrivals)
SELECT severity_score,
       COUNT(*)                          AS patients,
       ROUND(AVG(wait_fifo), 1)          AS avg_wait_fifo,
       ROUND(AVG(wait_priority), 1)      AS avg_wait_priority,
       ROUND(100.0 * (AVG(wait_priority) - AVG(wait_fifo)) / AVG(wait_fifo), 1) AS pct_change
FROM sim_policy_comparison
GROUP BY severity_score
UNION ALL
SELECT NULL, COUNT(*), ROUND(AVG(wait_fifo), 1), ROUND(AVG(wait_priority), 1),
       ROUND(100.0 * (AVG(wait_priority) - AVG(wait_fifo)) / AVG(wait_fifo), 1)
FROM sim_policy_comparison;
