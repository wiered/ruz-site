# ruz-site

## Run

```powershell
python -m ruzsite.main
```

`src/ruzsite/main.py` imports `app` from `src/ruzsite/app.py` and starts Uvicorn.

## User activity

Successful Telegram login and authenticated requests to `/`, `/schedule`, and
`/settings` (including search, group and subgroup changes) queue a background
activity update. Static files, health checks and anonymous visits are excluded.
There is no periodic heartbeat: an idle open tab does not generate activity.

The site reads `last_used_at` using `ruz-client` and calls the bodyless
`PUT /api/user/{id}/touch` only when the timestamp is absent or at least five
minutes old. Redis provides a per-user lock across workers and a cooldown;
failed updates are retried on the next qualifying request. API and Redis errors
are logged and do not fail the user's action. The API key stays on the server.
User profiles are not cached by the site, so no profile invalidation is needed.

This feeds the backend's shared bot/site activity timestamp for DAU/MAU; it does
not store daily history or calculate separate site-only metrics.
