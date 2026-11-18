"""Python port of the triage logic in the source app (src/lib/ai.ts).

Kept rule-for-rule identical so analytics on this data reflect how the
production queue actually prioritises patients.
"""

CRITICAL_KEYWORDS = ["chest pain", "breathing difficulty", "unconscious",
                     "severe bleeding", "stroke", "heart attack"]
SERIOUS_KEYWORDS = ["shortness of breath", "high fever", "severe pain",
                    "vomiting blood", "confusion"]
SEVERITY_LABELS = {1: "Minimal", 2: "Mild", 3: "Moderate", 4: "Severe", 5: "Critical"}


def severity_points(fever, systolic_bp, spo2, age, symptoms=""):
    points = 0
    if fever >= 40: points += 3
    elif fever >= 39: points += 2
    elif fever >= 38: points += 1

    if systolic_bp >= 180 or systolic_bp < 80: points += 3
    elif systolic_bp >= 160: points += 2
    elif systolic_bp >= 140: points += 1

    if spo2 < 90: points += 4
    elif spo2 < 94: points += 2
    elif spo2 < 96: points += 1

    if age >= 75: points += 2
    elif age >= 60: points += 1
    elif age <= 5: points += 2

    s = (symptoms or "").lower()
    if any(k in s for k in CRITICAL_KEYWORDS): points += 3
    elif any(k in s for k in SERIOUS_KEYWORDS): points += 2
    return points


def predict_severity(fever, systolic_bp, spo2, age, symptoms=""):
    p = severity_points(fever, systolic_bp, spo2, age, symptoms)
    if p >= 10: return 5
    if p >= 7: return 4
    if p >= 4: return 3
    if p >= 2: return 2
    return 1


def calculate_fatigue_pct(patients_handled, avg_consult_min, shift_hours):
    """Staff Fatigue Index (% of shift minutes spent consulting), as in ai.ts."""
    return min(100, round(patients_handled * avg_consult_min / (shift_hours * 60) * 100))
