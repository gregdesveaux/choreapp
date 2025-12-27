import base64
import json
import os
import smtplib
import ssl
import threading
import time
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse
import http.client
import urllib.parse
import sqlite3

DATA_DIR = Path("data")
PUBLIC_DIR = Path("public")
DB_PATH = DATA_DIR / "choreapp.db"
DEFAULT_PORT = int(os.environ.get("PORT", "8000"))


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_iso(timestamp: Optional[str]) -> Optional[datetime]:
    if not timestamp:
        return None
    return datetime.fromisoformat(timestamp)


class Database:
    def __init__(self, path: Path):
        DATA_DIR.mkdir(exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()
        self._seed_defaults()

    def _init_schema(self) -> None:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS kids (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT,
                phone TEXT
            );
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS chores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                frequency_days INTEGER NOT NULL
            );
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS assignments (
                chore_id INTEGER PRIMARY KEY,
                assigned_to INTEGER NOT NULL,
                due_date TEXT NOT NULL,
                last_completed_at TEXT,
                last_notified_at TEXT,
                FOREIGN KEY(chore_id) REFERENCES chores(id),
                FOREIGN KEY(assigned_to) REFERENCES kids(id)
            );
            """
        )
        self.conn.commit()

    def _seed_defaults(self) -> None:
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM kids")
        kid_count = cursor.fetchone()[0]
        if kid_count == 0:
            kid1_name = os.environ.get("KID1_NAME", "Alex")
            kid2_name = os.environ.get("KID2_NAME", "Sam")
            cursor.execute(
                "INSERT INTO kids (name, email, phone) VALUES (?, ?, ?)",
                (kid1_name, os.environ.get("KID1_EMAIL"), os.environ.get("KID1_PHONE")),
            )
            cursor.execute(
                "INSERT INTO kids (name, email, phone) VALUES (?, ?, ?)",
                (kid2_name, os.environ.get("KID2_EMAIL"), os.environ.get("KID2_PHONE")),
            )

        cursor.execute("SELECT COUNT(*) FROM chores")
        chore_count = cursor.fetchone()[0]
        if chore_count == 0:
            cursor.execute(
                "INSERT INTO chores (name, frequency_days) VALUES (?, ?)",
                ("Dishes", 1),
            )
            cursor.execute(
                "INSERT INTO chores (name, frequency_days) VALUES (?, ?)",
                ("Trash & Recycling", 3),
            )
            cursor.execute(
                "INSERT INTO chores (name, frequency_days) VALUES (?, ?)",
                ("Room Tidy", 3),
            )

        cursor.execute("SELECT id FROM kids ORDER BY id")
        kids = [row[0] for row in cursor.fetchall()]
        cursor.execute("SELECT id, frequency_days FROM chores ORDER BY id")
        chores = cursor.fetchall()
        now_iso = utc_now().isoformat()
        for index, chore in enumerate(chores):
            cursor.execute(
                "SELECT 1 FROM assignments WHERE chore_id = ?",
                (chore[0],),
            )
            if cursor.fetchone() is None:
                assigned_to = kids[index % len(kids)]
                cursor.execute(
                    "INSERT INTO assignments (chore_id, assigned_to, due_date) VALUES (?, ?, ?)",
                    (chore[0], assigned_to, now_iso),
                )

        self.conn.commit()

    def list_chores(self) -> List[Dict]:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT c.id, c.name, c.frequency_days, a.assigned_to, a.due_date, a.last_completed_at, a.last_notified_at,
                   k.name as kid_name, k.email as kid_email, k.phone as kid_phone
            FROM chores c
            JOIN assignments a ON a.chore_id = c.id
            JOIN kids k ON k.id = a.assigned_to
            ORDER BY c.id
            """
        )
        now = utc_now()
        chores = []
        for row in cursor.fetchall():
            due = datetime.fromisoformat(row[4])
            chores.append(
                {
                    "id": row[0],
                    "name": row[1],
                    "frequencyDays": row[2],
                    "assignedTo": {
                        "id": row[3],
                        "name": row[7],
                        "email": row[8],
                        "phone": row[9],
                    },
                    "dueDate": row[4],
                    "lastCompletedAt": row[5],
                    "lastNotifiedAt": row[6],
                    "isOverdue": due < now,
                    "isDueSoon": due <= now + timedelta(hours=4),
                }
            )
        return chores

    def _other_kid(self, current_kid: int) -> int:
        cursor = self.conn.cursor()
        cursor.execute("SELECT id FROM kids ORDER BY id")
        kid_ids = [row[0] for row in cursor.fetchall()]
        if len(kid_ids) < 2:
            return current_kid
        if current_kid == kid_ids[0]:
            return kid_ids[1]
        return kid_ids[0]

    def complete_chore(self, chore_id: int) -> Optional[Dict]:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT c.id, c.name, c.frequency_days, a.assigned_to
            FROM chores c
            JOIN assignments a ON a.chore_id = c.id
            WHERE c.id = ?
            """,
            (chore_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None

        current_kid = row[3]
        next_kid = self._other_kid(current_kid)
        new_due = utc_now() + timedelta(days=row[2])
        now_iso = utc_now().isoformat()

        cursor.execute(
            """
            UPDATE assignments
            SET assigned_to = ?, due_date = ?, last_completed_at = ?, last_notified_at = NULL
            WHERE chore_id = ?
            """,
            (next_kid, new_due.isoformat(), now_iso, chore_id),
        )
        self.conn.commit()
        return {
            "id": row[0],
            "name": row[1],
            "frequencyDays": row[2],
            "previousKid": current_kid,
            "assignedTo": next_kid,
            "dueDate": new_due.isoformat(),
            "completedAt": now_iso,
        }

    def fetch_due_assignments(self, now: datetime) -> List[Dict]:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT c.id as chore_id, c.name, c.frequency_days, a.due_date, a.last_notified_at,
                   k.id as kid_id, k.name as kid_name, k.email, k.phone
            FROM assignments a
            JOIN chores c ON c.id = a.chore_id
            JOIN kids k ON k.id = a.assigned_to
            WHERE a.due_date <= ?
            """,
            (now.isoformat(),),
        )
        return [dict(row) for row in cursor.fetchall()]

    def mark_notified(self, chore_id: int, timestamp: datetime) -> None:
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE assignments SET last_notified_at = ? WHERE chore_id = ?",
            (timestamp.isoformat(), chore_id),
        )
        self.conn.commit()


def bool_env(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


class Notifier:
    def __init__(self) -> None:
        self.email_host = os.environ.get("SMTP_HOST")
        self.email_port = int(os.environ.get("SMTP_PORT", "587"))
        self.email_user = os.environ.get("SMTP_USER")
        self.email_password = os.environ.get("SMTP_PASSWORD")
        self.email_from = os.environ.get("SMTP_FROM", self.email_user or "choreapp@example.com")
        self.email_use_tls = bool_env("SMTP_USE_TLS", True)

        self.twilio_sid = os.environ.get("TWILIO_ACCOUNT_SID")
        self.twilio_token = os.environ.get("TWILIO_AUTH_TOKEN")
        self.twilio_from = os.environ.get("TWILIO_FROM_NUMBER")

    def _send_email(self, to_address: str, subject: str, body: str) -> bool:
        if not self.email_host or not to_address:
            return False
        message = f"From: {self.email_from}\nTo: {to_address}\nSubject: {subject}\n\n{body}"
        try:
            with smtplib.SMTP(self.email_host, self.email_port, timeout=10) as server:
                if self.email_use_tls:
                    context = ssl.create_default_context()
                    server.starttls(context=context)
                if self.email_user and self.email_password:
                    server.login(self.email_user, self.email_password)
                server.sendmail(self.email_from, [to_address], message)
            print(f"[notify] Email sent to {to_address}")
            return True
        except Exception as exc:  # noqa: BLE001
            print(f"[notify] Failed to send email to {to_address}: {exc}")
            return False

    def _send_sms(self, to_number: str, body: str) -> bool:
        if not (self.twilio_sid and self.twilio_token and self.twilio_from and to_number):
            return False
        try:
            payload = urllib.parse.urlencode(
                {
                    "To": to_number,
                    "From": self.twilio_from,
                    "Body": body,
                }
            )
            auth = base64.b64encode(f"{self.twilio_sid}:{self.twilio_token}".encode()).decode()
            headers = {
                "Authorization": f"Basic {auth}",
                "Content-Type": "application/x-www-form-urlencoded",
            }
            connection = http.client.HTTPSConnection("api.twilio.com", timeout=10)
            endpoint = f"/2010-04-01/Accounts/{self.twilio_sid}/Messages.json"
            connection.request("POST", endpoint, payload, headers)
            response = connection.getresponse()
            success = 200 <= response.status < 300
            connection.close()
            if success:
                print(f"[notify] SMS sent to {to_number}")
            else:
                print(f"[notify] Failed SMS {response.status}: {response.read()[:200]}")
            return success
        except Exception as exc:  # noqa: BLE001
            print(f"[notify] Failed to send SMS to {to_number}: {exc}")
            return False

    def notify(self, kid: Dict, chore: str, due_date: datetime) -> None:
        subject = f"Chore due: {chore}"
        body = (
            f"Hi {kid['kid_name']},\n\n"
            f"It's your turn to handle '{chore}'. The chore is due now (scheduled for {due_date.isoformat()})."
        )
        sent = False
        if kid.get("email"):
            sent = self._send_email(kid["email"], subject, body)
        if kid.get("phone") and not sent:
            sent = self._send_sms(kid["phone"], body)
        if not sent:
            print(f"[notify] No notification channel configured for {kid.get('kid_name')}")


class NotificationScheduler(threading.Thread):
    def __init__(self, db: Database, notifier: Notifier, interval_seconds: int = 60):
        super().__init__(daemon=True)
        self.db = db
        self.notifier = notifier
        self.interval_seconds = interval_seconds
        self.enabled = bool_env("ENABLE_NOTIFICATIONS", True)

    def run(self) -> None:  # noqa: D401
        while True:
            try:
                if self.enabled:
                    self._check_and_notify()
            except Exception as exc:  # noqa: BLE001
                print(f"[notify] Scheduler error: {exc}")
            time.sleep(self.interval_seconds)

    def _check_and_notify(self) -> None:
        now = utc_now()
        due_assignments = self.db.fetch_due_assignments(now)
        for assignment in due_assignments:
            due_date = parse_iso(assignment.get("due_date"))
            last_notified = parse_iso(assignment.get("last_notified_at"))
            if last_notified and due_date and last_notified >= due_date:
                continue
            if due_date is None:
                continue
            self.notifier.notify(assignment, assignment["name"], due_date)
            self.db.mark_notified(assignment["chore_id"], now)


class RequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PUBLIC_DIR), **kwargs)

    def _json_response(self, data: Dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        payload = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/chores":
            chores = self.server.database.list_chores()  # type: ignore[attr-defined]
            self._json_response({"chores": chores})
            return
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        segments = [segment for segment in parsed.path.split("/") if segment]
        if len(segments) == 3 and segments[0] == "api" and segments[1] == "chores" and segments[2].isdigit():
            chore_id = int(segments[2])
            result = self.server.database.complete_chore(chore_id)  # type: ignore[attr-defined]
            if result is None:
                self._json_response({"error": "Chore not found"}, HTTPStatus.NOT_FOUND)
            else:
                self._json_response({"completed": result})
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Unknown endpoint")

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        print("[server]", format % args)


def ensure_public_files() -> None:
    PUBLIC_DIR.mkdir(exist_ok=True)
    index_file = PUBLIC_DIR / "index.html"
    if not index_file.exists():
        index_file.write_text(
            "<!DOCTYPE html><html><body><h1>Chore App</h1></body></html>",
            encoding="utf-8",
        )


def serve() -> None:
    ensure_public_files()
    db = Database(DB_PATH)
    notifier = Notifier()
    scheduler = NotificationScheduler(db, notifier)
    scheduler.start()

    server_address = ("", DEFAULT_PORT)
    httpd = ThreadingHTTPServer(server_address, RequestHandler)
    httpd.database = db  # type: ignore[attr-defined]
    print(f"[server] Running on http://0.0.0.0:{DEFAULT_PORT}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("[server] Shutting down")
        httpd.server_close()


if __name__ == "__main__":
    serve()
