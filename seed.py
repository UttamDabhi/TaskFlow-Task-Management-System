"""Initialise the TaskFlow database and add demo accounts and sample tasks.

Safe to run any number of times:
  * demo users are only created when their email does not exist yet
    (existing passwords, names and roles are never overwritten)
  * sample tasks are inserted once, tracked by a flag stored in the database
"""
import sqlite3
from datetime import date, timedelta

from werkzeug.security import generate_password_hash

from app import default_db_path, init_db, load_env_file, now_iso

DEMO_USERS = [
    ("Admin User", "admin@example.com", "Admin123!", "admin"),
    ("Manager User", "manager@example.com", "Manager123!", "manager"),
    ("Demo User", "user@example.com", "User12345!", "user"),
]

# (title, description, status, priority, assignee email, due in N days)
SAMPLE_TASKS = [
    ("Fix production login outage",
     "Users report 500 errors on the login page after the last deploy. Roll back or patch ASAP.",
     "In Progress", "Urgent", "manager@example.com", 0),
    ("Prepare Q4 sprint planning deck",
     "Summarise velocity, carry-over work and proposed goals for the Q4 planning meeting.",
     "To Do", "High", "user@example.com", 3),
    ("Write API documentation for task endpoints",
     "Document request/response examples for the /api/tasks endpoints in the README.",
     "To Do", "Low", "user@example.com", 14),
    ("Review customer feedback survey results",
     "Go through the latest survey, tag recurring themes and share a short summary with the team.",
     "In Progress", "Medium", "user@example.com", 5),
    ("Upgrade dependencies and run regression tests",
     "Update Flask and Werkzeug to the latest patch versions and re-run the automated test suite.",
     "Completed", "Medium", "manager@example.com", -2),
    ("Investigate failed payment webhook",
     "Several customer payments were not confirmed. Check webhook logs and reproduce the failure.",
     "To Do", "High", "manager@example.com", 1),
    ("Design onboarding checklist for new hires",
     "Nice-to-have: a one-page checklist covering accounts, tooling and first-week goals.",
     "To Do", "Low", None, 30),
    ("Set up weekly database backup",
     "Create a scheduled backup of the SQLite database and verify a restore works.",
     "Completed", "High", "admin@example.com", -5),
]


def seed_database(db_path=None):
    """Create tables, demo users and sample tasks. Returns a small summary dict."""
    db_path = db_path or default_db_path()
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    summary = {"users_created": 0, "users_existing": 0, "tasks_created": 0}
    try:
        for name, email, password, role in DEMO_USERS:
            if conn.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
                summary["users_existing"] += 1
                continue
            conn.execute(
                "INSERT INTO users (name, email, password_hash, role, created_at) VALUES (?, ?, ?, ?, ?)",
                (name, email, generate_password_hash(password), role, now_iso()),
            )
            summary["users_created"] += 1

        seeded = conn.execute("SELECT 1 FROM meta WHERE key = 'sample_tasks_seeded'").fetchone()
        if not seeded:
            ids = {r["email"]: r["id"] for r in conn.execute("SELECT id, email FROM users")}
            creator = ids.get("manager@example.com") or ids.get("admin@example.com")
            timestamp = now_iso()
            for title, description, status, priority, assignee_email, due_in in SAMPLE_TASKS:
                conn.execute(
                    "INSERT INTO tasks (title, description, status, priority, assignee_id, creator_id,"
                    " due_date, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (title, description, status, priority, ids.get(assignee_email), creator,
                     (date.today() + timedelta(days=due_in)).isoformat(), timestamp, timestamp),
                )
                summary["tasks_created"] += 1
            conn.execute("INSERT INTO meta (key, value) VALUES ('sample_tasks_seeded', '1')")
        conn.commit()
    finally:
        conn.close()
    return summary


if __name__ == "__main__":
    load_env_file()
    path = default_db_path()
    result = seed_database(path)
    print(f"Database ready: {path}")
    print(f"  Demo users created: {result['users_created']} (already existed: {result['users_existing']})")
    print(f"  Sample tasks created: {result['tasks_created']}")
    print("\nDemo logins:")
    for _name, email, password, role in DEMO_USERS:
        print(f"  {role:<8} {email} / {password}")
