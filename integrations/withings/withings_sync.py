import csv
import os
import sys
import time
import json
import base64
import urllib.parse as up
from datetime import datetime, timedelta, timezone
import requests
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
load_dotenv()

CLIENT_ID = os.getenv("WITHINGS_CLIENT_ID")
CLIENT_SECRET = os.getenv("WITHINGS_CLIENT_SECRET")
REDIRECT_URI = os.getenv("WITHINGS_REDIRECT_URI")  # GitHub Pages URL
REFRESH_TOKEN = os.getenv("WITHINGS_REFRESH_TOKEN")  # set after first run

WEIGHT_CSV = os.getenv("WEIGHT_CSV", "knowledge/weight_log.csv")
ACTIVITY_CSV = os.getenv("ACTIVITY_CSV", "knowledge/activity_log.csv")

# Date window to fetch, default last 14 days
DAYS_BACK = int(os.getenv("WITHINGS_DAYS_BACK", "14"))

TOKEN_URL = "https://wbsapi.withings.net/v2/oauth2"
MEASURE_URL = "https://wbsapi.withings.net/measure"
ACTIVITY_URL = "https://wbsapi.withings.net/v2/measure"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_utc():
    return datetime.now(timezone.utc)

def _ts(dt):
    return int(dt.timestamp())

def _datestr(d):
    return d.strftime("%Y-%m-%d")

def ensure_csv(path, header):
    exists = os.path.isfile(path)
    if not exists:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(header)

def upsert_row_by_date(path, header, row_dict, date_field="date"):
    # Load all
    rows = []
    index = -1
    ensure_csv(path, header)
    with open(path, "r", newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for i, row in enumerate(r):
            rows.append(row)
            if row.get(date_field) == row_dict.get(date_field):
                index = i
    # Upsert
    if index >= 0:
        rows[index] = {**rows[index], **row_dict}
    else:
        rows.append(row_dict)
        rows.sort(key=lambda x: x.get(date_field))
    # Write back
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=header)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in header})

def exchange_code_for_tokens(code):
    data = {
        "action": "requesttoken",
        "grant_type": "authorization_code",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code": code,
        "redirect_uri": REDIRECT_URI,
    }
    resp = requests.post(TOKEN_URL, data=data, timeout=30)
    resp.raise_for_status()
    js = resp.json()
    if js.get("status") != 0:
        raise RuntimeError(f"Token exchange failed: {js}")
    body = js["body"]
    return body["access_token"], body["refresh_token"], body["expires_in"]

def refresh_access_token(refresh_token):
    data = {
        "action": "requesttoken",
        "grant_type": "refresh_token",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": refresh_token,
    }
    resp = requests.post(TOKEN_URL, data=data, timeout=30)
    resp.raise_for_status()
    js = resp.json()
    if js.get("status") != 0:
        raise RuntimeError(f"Refresh failed: {js}")
    body = js["body"]
    return body["access_token"], body["refresh_token"], body["expires_in"]

def with_auth_headers(token):
    return {"Authorization": f"Bearer {token}"}

def fetch_weight_series(token, start_date, end_date):
    # Withings body measures - weight, bodyfat etc
    params = {
        "action": "getmeas",
        "meastypes": "1,6,76,77",  # weight=1, fat_ratio=6, muscle_mass=76, hydration=77
        "category": 1,
        "startdate": _ts(start_date),
        "enddate": _ts(end_date),
    }
    r = requests.get(MEASURE_URL, headers=with_auth_headers(token), params=params, timeout=30)
    r.raise_for_status()
    js = r.json()
    if js.get("status") != 0:
        raise RuntimeError(f"getmeas failed: {js}")
    return js.get("body", {}).get("measuregrps", [])

def fetch_daily_activity(token, start_date, end_date):
    # Withings daily activity summary
    params = {
        "action": "getactivity",
        "startdateymd": _datestr(start_date),
        "enddateymd": _datestr(end_date),
    }
    r = requests.get(ACTIVITY_URL, headers=with_auth_headers(token), params=params, timeout=30)
    r.raise_for_status()
    js = r.json()
    if js.get("status") != 0:
        raise RuntimeError(f"getactivity failed: {js}")
    return js.get("body", {}).get("activities", [])

def mm_to_kg(value, unit_pow10):
    # Withings returns values with 'unit' like -3 meaning divide by 10^3
    return value * (10 ** unit_pow10)

def first_value_by_type(measures, type_id):
    for m in measures:
        if m.get("type") == type_id:
            return mm_to_kg(m["value"], m["unit"])
    return None

def run_sync(access_token):
    end_date = _now_utc().date()
    start_date = end_date - timedelta(days=DAYS_BACK)

    # Prepare CSVs
    weight_header = ["date","weight_kg","body_fat_pct","muscle_mass_kg","water_pct","source","notes"]
    activity_header = ["date","steps","exercise_minutes","avg_hr_bpm","resting_hr_bpm","calories_out","workout_type","workout_duration_min","source"]

    ensure_csv(WEIGHT_CSV, weight_header)
    ensure_csv(ACTIVITY_CSV, activity_header)

    # Weight and composition
    for grp in fetch_weight_series(access_token, start_date, end_date):
        ts = datetime.fromtimestamp(grp["date"], tz=timezone.utc).date()
        measures = grp.get("measures", [])
        weight = first_value_by_type(measures, 1)
        fat_pct = first_value_by_type(measures, 6)
        muscle_kg = first_value_by_type(measures, 76)
        water_pct = first_value_by_type(measures, 77)
        row = {
            "date": _datestr(ts),
            "weight_kg": f"{weight:.2f}" if weight is not None else "",
            "body_fat_pct": f"{fat_pct:.2f}" if fat_pct is not None else "",
            "muscle_mass_kg": f"{muscle_kg:.2f}" if muscle_kg is not None else "",
            "water_pct": f"{water_pct:.2f}" if water_pct is not None else "",
            "source": "withings",
            "notes": "",
        }
        upsert_row_by_date(WEIGHT_CSV, weight_header, row)

    # Daily activity
    for act in fetch_daily_activity(access_token, start_date, end_date):
        date = act.get("date")
        row = {
            "date": date,
            "steps": act.get("steps", ""),
            "exercise_minutes": act.get("active_minutes", act.get("soft", "")),
            "avg_hr_bpm": act.get("hr_average", ""),
            "resting_hr_bpm": act.get("hr_min", ""),
            "calories_out": act.get("calories", ""),
            "workout_type": "",  # can be enriched later
            "workout_duration_min": "",
            "source": "withings",
        }
        upsert_row_by_date(ACTIVITY_CSV, activity_header, row)

if __name__ == "__main__":
    if not CLIENT_ID or not CLIENT_SECRET or not REDIRECT_URI:
        print("Missing env vars. Set WITHINGS_CLIENT_ID, WITHINGS_CLIENT_SECRET, WITHINGS_REDIRECT_URI.")
        sys.exit(2)

    if not REFRESH_TOKEN:
        # First run, need a one-time CODE
        if len(sys.argv) < 2:
            auth_url = (
                "https://account.withings.com/oauth2_user/authorize2?"
                + up.urlencode({
                    "response_type": "code",
                    "client_id": CLIENT_ID,
                    "state": "ric_state_123",
                    "scope": "user.metrics,user.activity,user.info",
                    "redirect_uri": REDIRECT_URI,
                })
            )
            print("\nOpen this URL, approve, and copy the code shown on your GitHub Pages page:\n")
            print(auth_url)
            print("\nThen re-run:\npython withings_sync.py <PASTE_CODE_HERE>\n")
            sys.exit(0)
        code = sys.argv[1]
        access_token, refresh_token, expires = exchange_code_for_tokens(code)
        print("Store this as WITHINGS_REFRESH_TOKEN secret:\n", refresh_token)
        run_sync(access_token)
    else:
        access_token, refresh_token, expires = refresh_access_token(REFRESH_TOKEN)
        print("Token refreshed OK")
        # In CI we cannot persist a new secret automatically, so just output it if it rotates.
        if refresh_token and refresh_token != REFRESH_TOKEN:
            print("New refresh token, update your GitHub Secret WITHINGS_REFRESH_TOKEN:\n", refresh_token)
        run_sync(access_token)
