# NotebookLM Auth Troubleshooting

## Problem

The weekly psychiatry review automation runs on a VM every Sunday, but frequently fails with **"Authentication expired or invalid"** errors. This prevents podcasts from being generated.

## Root Cause

- NotebookLM uses Playwright browser automation with session cookies
- Google enforces short session lifetimes for security reasons
- Cookies in `storage_state.json` expire after ~2 hours of inactivity
- The VM has no way to perform interactive Google login (headless environment)
- `refresh_auth()` requires an already-valid session to work

## Symptoms

- `notebooklm list` returns: "Authentication expired or invalid. Redirected to: https://accounts.google.com/..."
- Weekly review runs but skips all NotebookLM operations (podcasts are NOT generated)
- Only markdown summaries are saved, no audio artifacts

## Solutions

### Solution 1: Manual Auth Refresh (Weekly)

Before each Sunday run (or weekly), refresh auth from your local machine:

```bash
# On your local machine
notebooklm login
# Complete Google login in the browser

# Upload fresh session to Secret Manager
./vm/update_auth.sh
```

Then the VM will use the fresh session on the next run.

### Solution 2: Try Refresh in Code

The `weekly_review.py` script now attempts to call `client.refresh_auth()` to renew tokens:

```python
async with await NotebookLMClient.from_storage() as client:
    tokens = await client.refresh_auth()  # Get fresh CSRF tokens
```

This works **only if there's a valid starting session**. If completely expired, it will fail.

### Solution 3: Automatic Cron Refresh (Recommended)

Run `notebooklm login` automatically via a scheduled task on your local machine weekly:

1. Set up a weekly cron job on your local machine
2. Have it run `notebooklm login` in headless/auto mode (if supported)
3. Automatically upload to Secret Manager with `./vm/update_auth.sh`

## Testing

Test if auth is working:

```bash
# Quick diagnostic
./vm/test_auth.sh

# Or manually
notebooklm list --json
```

Expected output if auth is valid:
```json
{
  "notebooks": [
    { "id": "...", "title": "..." },
    ...
  ]
}
```

Expected output if auth is expired:
```json
{
  "error": true,
  "message": "Authentication expired or invalid..."
}
```

## Files Modified for Auth Handling

- `scripts/weekly_review.py` (lines 1060-1084): Added `refresh_auth()` call during pre-check
- `vm/run_review.sh`: Added session verification before running the script
- `vm/test_auth.sh`: Improved diagnostics for auth status
- `vm/update_auth.sh`: NEW — Tool to upload fresh session to Secret Manager

## Next Steps

1. **Immediate**: Run `notebooklm login` on your local machine, then `./vm/update_auth.sh`
2. **Verify**: Run `./vm/test_auth.sh` to confirm auth works
3. **Monitor**: Check if Sunday's run generates podcasts
4. **Long-term**: Set up weekly auth refresh (see Solution 3 above)

## References

- NotebookLM docs: `docs/configuration.md`
- NotebookLM auth: `docs/troubleshooting.md`
- notebooklm-py refresh method: `NotebookLMClient.refresh_auth()`
