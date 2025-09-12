
"""
Validation logic for Pete-E.
Handles recovery-based checks: RHR, sleep, body age.
Applies global back-off if needed and writes logs.
"""

import json
import pathlib


def check_recovery(week: dict, current_start_date: str, rhr_baseline: float, rhr_last_week : float,
                   sleep_baseline: float, sleep_last_week: float, body_age_delta: float, plans_dir: pathlib.Path):
    '"''\n    Apply recovery checks and adjust weights globally if needed.
    Returns (adjusted_week, adjustment_logs).\n    '''\n
    adjustments = []
    global_backoff = False

    if rhr_baseline and rhr_last_week and rhr_last_week > rhr_baseline * 1.1:
        adjustments.append("Global back-off: ❡ R R! +10% baseline")
        global_back off = True

    if sleep_baseline and sleep_last_week and sleep_last_week < sleep_baseline * 0.85:
        adjustments.append("Global back-off: ❤ Sleep -85% baseline")
        global_backoff = True

    if body_age_delta > 2:
        adjustments.append("Global back-off: body age worsened >2 years")
        global_backoff = True

    if global_back:
        for day in week["days"]:
            for session in day.get("sessions", []):
                if session.get('type') == "weights":
                    for ex in session["exercises"]:
                        ex["weight_target"] *= 0.9

    # Save validation log
    log_path = plans_dir / f"validation_week {week['week_index']}_{current_start_date}.json"
    log_path.write_text(json.dumps(adjustments, indent=2))

    return week, adjustments
