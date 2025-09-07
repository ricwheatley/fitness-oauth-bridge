import json, pathlib, csv

WITHINGS_HIST = pathlib.Path("docs/withings/history.json")
APPLE_HIST    = pathlib.Path("docs/apple/history.json")
OUT_DIR       = pathlib.Path("docs/analytics")
CSV_PATH      = pathlib.Path("knowledge/body_age_log.csv")

def load_hist(p: pathlib.Path):
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []

def main():
    wh = load_hist(WITHINGS_HIST)
    ah = load_hist(APPLE_HIST)
    if not wh or not ah:
        print("Missing input data")
        return

    wm = {r.get("date"): r for r in wh if r.get("date")}
    am = {r.get("date"): r for r in ah if r.get("date")}
    dates = sorted(set(wm) | set(am))
    if not dates:
        return
    dates = dates[-7:]

    def to_float(v):
        try:
            if v in (None, ""):
                return None
            return float(v)
        except Exception:
            return None

    def avg_from(fn):
        vals = [to_float(fn(d)) for d in dates]
        vals = [v for v in vals if v is not None]
        return sum(vals) / len(vals) if vals else None

    weight  = avg_from(lambda d: wm.get(d, {}).get("weight_kg"))
    bodyfat = avg_from(lambda d: wm.get(d, {}).get("body_fat_pct"))
    steps   = avg_from(lambda d: am.get(d, {}).get("steps"))
    exmin   = avg_from(lambda d: am.get(d, {}).get("exercise_minutes"))
    c_act   = avg_from(lambda d: am.get(d, {}).get("calories_active"))
    c_rest  = avg_from(lambda d: am.get(d, {}).get("calories_resting"))
    c_tot   = avg_from(lambda d: am.get(d, {}).get("calories_total"))
    if c_tot is None and (c_act or c_rest):
        c_tot = (c_act or 0) + (c_rest or 0)
    rhr     = avg_from(lambda d: am.get(d, {}).get("hr_resting"))
    hravg   = avg_from(lambda d: am.get(d, {}).get("hr_avg"))
    sleepm  = avg_from(lambda d: (am.get(d, {}).get("sleep_minutes") or {}).get("asleep"))

    chrono_age = 44
    vo2 = None
    if rhr is not None:
        vo2 = 38 - 0.15 * (chrono_age - 40) - 0.15 * ((rhr or 60) - 60) + 0.01 * (exmin or 0)
    if vo2 is None:
        vo2 = 35
    crf = max(0, min(100, ((vo2 - 20) / (60 - 20)) * 100))

    if bodyfat is None:
        body_comp = 50
    elif bodyfat <= 15:
        body_comp = 100
    elif bodyfat >= 30:
        body_comp = 0
    else:
        body_comp = (30 - bodyfat) / (30 - 15) * 100

    steps_score = 0 if steps is None else max(0, min(100, (steps / 12000) * 100))
    ex_score    = 0 if exmin is None else max(0, min(100, (exmin / 30) * 100))
    activity    = 0.6 * steps_score + 0.4 * ex_score

    if sleepm is None:
        sleep_score = 50
    else:
        diff = abs(sleepm - 450)
        sleep_score = max(0, min(100, 100 - (diff / 150) * 60))

    if rhr is None:
        rhr_score = 50
    elif rhr <= 55:
        rhr_score = 90
    elif rhr <= 60:
        rhr_score = 80
    elif rhr <= 70:
        rhr_score = 60
    elif rhr <= 80:
        rhr_score = 40
    else:
        rhr_score = 20

    recovery = 0.66 * sleep_score + 0.34 * rhr_score

    composite = 0.40 * crf + 0.25 * body_comp + 0.20 * activity + 0.15 * recovery
    body_age = chrono_age - 0.2 * (composite - 50)
    cap_min = chrono_age - 10
    cap = False
    if body_age < cap_min:
        body_age = cap_min
        cap = True
    age_delta = body_age - chrono_age

    out = {
        "date": dates[-1],
        "inputs_window_days": 7,
        "subscores": {
            "crf": round(crf, 1),
            "body_comp": round(body_comp, 1),
            "activity": round(activity, 1),
            "recovery": round(recovery, 1),
        },
        "composite": round(composite, 1),
        "body_age_years": round(body_age, 1),
        "age_delta_years": round(age_delta, 1),
        "assumptions": {"used_vo2max_direct": False, "cap_minus_10_applied": cap},
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "body_age.json").write_text(json.dumps(out, indent=2), encoding="utf-8")

    hist_p = OUT_DIR / "history.json"
    try:
        hist = json.loads(hist_p.read_text()) if hist_p.exists() else []
    except Exception:
        hist = []
    hist = [h for h in hist if h.get("date") != out["date"]]
    hist.append(out)
    hist = sorted(hist, key=lambda x: x["date"])[-180:]
    hist_p.write_text(json.dumps(hist, indent=2), encoding="utf-8")

    hdr = ["date", "body_age_years", "age_delta_years", "composite", "crf", "body_comp", "activity", "recovery"]
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    rows = {}
    try:
        with open(CSV_PATH, "r", newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                rows[r["date"]] = r
    except FileNotFoundError:
        pass
    rows[out["date"]] = {
        "date": out["date"],
        "body_age_years": out["body_age_years"],
        "age_delta_years": out["age_delta_years"],
        "composite": out["composite"],
        "crf": out["subscores"]["crf"],
        "body_comp": out["subscores"]["body_comp"],
        "activity": out["subscores"]["activity"],
        "recovery": out["subscores"]["recovery"],
    }
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=hdr)
        w.writeheader()
        for k in sorted(rows):
            w.writerow(rows[k])

    print(json.dumps(out, indent=2))

if __name__ == "__main__":
    main()
