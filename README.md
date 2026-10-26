# TaskFlow - Task Management System

A role-based task manager built with **Python, Flask, SQLite, HTML, CSS and JavaScript**.
Candidate: Uttam Dabhi - Practical assignment, 26 October 2026.

No paid services, no API keys. The only dependency is Flask.

## Features

- Login, registration, logout with hashed passwords and secure session cookies
- Roles enforced **on the backend**: Admin, Manager, User (new sign-ups are always *User*)
- Task CRUD with title, description, status, priority, assignee, due date, creator, created/updated timestamps
- Statuses: To Do, In Progress, Completed - Priorities: Low, Medium, High, Urgent
- Search by title; filter by status, priority and assignee; refresh button
- Dashboard statistics: total, pending, in progress, completed, urgent (open)
- Loading indicators, empty states, error messages with a retry button, toast notifications
- Admin user management (change roles, delete users)
- **AI Assist** - a *rule-based* priority recommendation (keywords, negations and due dates).
  It is not an AI language model and makes no network calls.
- Responsive layout with a collapsible sidebar on phones

## Permissions

| Action | Admin | Manager | User |
|---|:---:|:---:|:---:|
| View tasks | all | all | only tasks assigned to them |
| Create / edit / delete / assign tasks | yes | yes | no |
| Update task **status** | any task | any task | own assigned tasks only |
| Manage users and roles | yes | no | no |
| Use AI Assist | yes | yes | yes |

## Setup on Windows 10/11 (PowerShell)

Requires Python 3.11 - 3.13 (check with `python --version`).

```powershell
# 1. Extract TaskFlow_Final_Uttam_Dabhi.zip (right-click > Extract All), then:
cd "$HOME\Downloads\TaskFlow_Final_Uttam_Dabhi\TaskFlow"

# 2. Create and activate a virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3. Install dependencies
python -m pip install -r requirements.txt

# 4. Create the database, demo users and sample tasks (safe to run again)
python seed.py

# 5. Start the app
python app.py
```

Open **http://127.0.0.1:5000** in your browser. Stop the server with `Ctrl+C`.

If PowerShell says *running scripts is disabled*, run this once and activate again:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

If `python` is not found, try `py -3 -m venv .venv` and `py -3 seed.py` / `py -3 app.py`.

## Demo accounts

| Role | Email | Password |
|---|---|---|
| Admin | admin@example.com | Admin123! |
| Manager | manager@example.com | Manager123! |
| User | user@example.com | User12345! |

`seed.py` only creates a demo account if its email does not exist yet and inserts the sample tasks only once.
Running it again never duplicates data or overwrites changed passwords. To start completely fresh, stop the app,
delete the `instance` folder and run `python seed.py` again.

## Run the automated tests

With the virtual environment active:

```powershell
python -m unittest discover -s tests -t . -v
```

The tests use a temporary database, so your real data is never touched. They cover authentication,
registration, role authorization, task CRUD, search/filters, statistics, the priority engine, its API endpoint
and seed idempotency.

## Configuration (optional)

Copy `.env.example` to `.env` to set `SECRET_KEY`, `DATABASE_PATH` and similar options:

```powershell
Copy-Item .env.example .env
```

## API overview

All endpoints return JSON. Errors look like `{"error": "message", "details": {"field": "problem"}}`.
Unauthenticated calls to `/api/*` return **401 JSON** (never an HTML redirect).

| Method | Endpoint | Notes |
|---|---|---|
| POST | `/api/auth/register`, `/api/auth/login`, `/api/auth/logout` | |
| GET | `/api/auth/me` | current user |
| GET | `/api/tasks?q=&status=&priority=&assignee=` | `assignee` is a user id or `unassigned` |
| POST | `/api/tasks` | admin, manager |
| GET / PATCH / PUT / DELETE | `/api/tasks/<id>` | see permission table |
| GET | `/api/tasks/stats` | dashboard counts |
| GET | `/api/users` | admin: full list; manager: for assigning; user: self |
| PATCH / DELETE | `/api/users/<id>` | admin only |
| POST | `/api/ai/suggest-priority` | body: `{"text": "...", "due_date": "YYYY-MM-DD"}` |

## Project structure

```
app.py            Flask app factory, auth, permissions, API
priority.py      Rule-based priority engine
seed.py           Idempotent database seed
templates/        base, login, register, dashboard, error
static/css|js/    style.css, common.js (API helper), auth.js, app.js
tests/            unittest suite
```

## Troubleshooting

- **Stuck on "Loading tasks..."** - this build shows an error with a *Try again* button instead; if you see it,
  check the PowerShell window running `python app.py` for the cause.
- **Port 5000 already in use** - stop the other program or edit the port in the last line of `app.py`.
- **Logged out unexpectedly after changing `SECRET_KEY`** - sessions are signed with it; just log in again.
