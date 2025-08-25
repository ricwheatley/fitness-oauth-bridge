# Integrations

## Withings → GitHub

### Setup
- OAuth App registered in Withings Dev Console
- Redirect: https://ricwheatley.github.io/fitness-oauth-bridge/
- GitHub Actions workflow exchanges code for refresh token
- Repo secret: WITHINGS_REFRESH_TOKEN

### Daily Sync
Workflow `.github/workflows/withings_sync.yml`:
- Refreshes token
- Pulls last 14 days of weight & activity
- Writes/updates:
  - `knowledge/weight_log.csv`
  - `knowledge/activity_log.csv`
- Commits and pushes if data changed

### Notes
- Codes are single-use, expire quickly
- Refresh token is long-lived
- If sync fails, rerun workflow manually
