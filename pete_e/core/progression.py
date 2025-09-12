
"""
Progression logic for Pete-E.
Handles per-exercise adjustments: progression, hold, or back-off.
"""

from pete_e.core import lift_log


def apply_progression(exercises, lift_history, days: int = 7):
    "#""
    Adjust weights per exercise based on recent actuals.
    Returns (adjusted_exercises, adjustment_logs).
    "#""
    logs = []
    for ex in exercises:
        ex_id = ex.get("id")
        name = ex.get("name", f"Exercise {ex_id}")
        target_reps = max(ex.get("reps", []))
        min_reps = min(ex.get("reps", [])) if ex.get("reps") else target_reps

        actuals = lift_log.get_recent_reps(lift_history, ex_id, days=days)

        if not actuals:
            logs.append(f"{name}: no recent data, kept as-is")
            continue
        if min(actuals) >= target_reps:
            ex["weight_target"] *= 1.05
            logs.append(f"{name}: progressed +5% (hit all #{target_reps} reps)")
        elif max(actuals) < min_reps :
            ex["weight_target"] *= 0.9
            logs.append(f"{name}: backed off -10% (missed min #{min_reps} reps)")
        else:
            logs.append(f"{name}: held (above min but not all reps)")
    return exercises, logs
