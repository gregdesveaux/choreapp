# Chore Swap

A lightweight two-kid chore tracker. Mark chores as done from the browser; the chore automatically rotates to the other child based on its schedule (daily or every N days). A background worker can notify kids by email or text when their chores are due.

## Features
- Web UI to view chores, see who is assigned, and mark items done.
- Automatic rotation to the other child on completion using chore-specific frequencies (daily or every 3 days by default).
- SQLite-backed storage seeded with two kids and starter chores.
- Notification worker that checks every minute and sends alerts via SMTP email or Twilio SMS when chores are due.
- Docker-friendly: no external dependencies beyond Python's standard library.

## Getting started (local)
1. Create a virtual environment if you want to isolate dependencies (optional—there are none to install).
2. Start the server:
   ```bash
   python app.py
   ```
3. Open http://localhost:8000 to use the app.

The server will create `data/choreapp.db` on first run, seed two kids (`Alex` and `Sam` by default), and seed three chores (Dishes, Trash & Recycling, Room Tidy).

## Configuration
Use environment variables to customize names and notifications.

### Kid names and contacts
- `KID1_NAME`, `KID2_NAME` — override default names.
- `KID1_EMAIL`, `KID2_EMAIL` — set email targets.
- `KID1_PHONE`, `KID2_PHONE` — set phone numbers for SMS.

### Email (SMTP)
- `SMTP_HOST` — SMTP server host.
- `SMTP_PORT` — SMTP port (default `587`).
- `SMTP_USER` / `SMTP_PASSWORD` — credentials if required.
- `SMTP_FROM` — from address (defaults to `SMTP_USER` or `choreapp@example.com`).
- `SMTP_USE_TLS` — set to `false` to disable `STARTTLS` (default `true`).

### SMS (Twilio)
- `TWILIO_ACCOUNT_SID`
- `TWILIO_AUTH_TOKEN`
- `TWILIO_FROM_NUMBER`

### Notification toggles
- `ENABLE_NOTIFICATIONS` — set to `false` to disable the background notifier (default `true`).
- `PORT` — override the server port (default `8000`).

An example `.env` configuration is provided in `.env.example`.

## Docker
Build and run the container (the app listens on port 8000 by default):

```bash
docker build -t chore-swap .
docker run -p 8000:8000 --env-file .env chore-swap
```

Persist the SQLite database by mounting `./data` to `/app/data` if desired:

```bash
docker run -p 8000:8000 --env-file .env -v $(pwd)/data:/app/data chore-swap
```

## API
- `GET /api/chores` — list chores with assignments and due info.
- `POST /api/chores/{id}` — mark a chore complete, rotate to the other kid, and schedule the next due date.

## Notes
- The scheduler checks for due chores every minute. It sends one notification per due window and resets when the chore is marked complete.
- Default frequencies are 1 day and 3 days. To change them, adjust the seeded chores or update the database directly.
