-- Star schema DDL for MySQL 8 (equivalent tables are built in SQLite by src/load_db.py)
CREATE DATABASE IF NOT EXISTS hospital_queue;
USE hospital_queue;

CREATE TABLE dim_department (
    department_id   INT PRIMARY KEY,
    department_name VARCHAR(50) NOT NULL UNIQUE
);

CREATE TABLE dim_doctor (
    doctor_id        VARCHAR(10) PRIMARY KEY,
    name             VARCHAR(100) NOT NULL,
    department_id    INT NOT NULL,
    shift_hours      TINYINT NOT NULL,
    base_consult_min DECIMAL(5,1),
    FOREIGN KEY (department_id) REFERENCES dim_department(department_id)
);

CREATE TABLE dim_date (
    date_key     INT PRIMARY KEY,          -- YYYYMMDD
    full_date    DATE NOT NULL,
    day_name     VARCHAR(10),
    day_of_week  TINYINT,                  -- 1 = Monday
    week_of_year TINYINT,
    month_name   VARCHAR(10),
    is_weekend   TINYINT(1)
);

CREATE TABLE fact_appointment (
    appointment_id       VARCHAR(10) PRIMARY KEY,
    date_key             INT NOT NULL,
    arrival_hour         TINYINT NOT NULL,
    created_at           DATETIME NOT NULL,
    patient_id           VARCHAR(10) NOT NULL,
    department_id        INT NOT NULL,
    doctor_id            VARCHAR(10) NULL,     -- NULL for no-show / cancelled
    token_number         INT,
    age                  TINYINT UNSIGNED,
    gender               CHAR(1),
    severity_score       TINYINT NOT NULL CHECK (severity_score BETWEEN 1 AND 5),
    fever                DECIMAL(4,1),
    spo2                 DECIMAL(4,1),
    bp_systolic          SMALLINT,
    status               ENUM('completed','no_show','cancelled') NOT NULL,
    waiting_time_min     DECIMAL(6,1),
    consult_duration_min DECIMAL(5,1),
    FOREIGN KEY (date_key)      REFERENCES dim_date(date_key),
    FOREIGN KEY (department_id) REFERENCES dim_department(department_id),
    FOREIGN KEY (doctor_id)     REFERENCES dim_doctor(doctor_id),
    INDEX ix_fact_date (date_key),
    INDEX ix_fact_doc  (doctor_id)
);

-- Load the CSVs in dashboard/powerbi_data/ with e.g.:
-- LOAD DATA LOCAL INFILE 'dashboard/powerbi_data/fact_appointment.csv'
--   INTO TABLE fact_appointment FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"'
--   IGNORE 1 LINES;
