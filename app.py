"""TaskFlow - Task Management System (Flask + SQLite)."""
import logging
import os
import re
import sqlite3
from datetime import date, datetime, timedelta, timezone
from functools import wraps
from pathlib import Path

from flask import Flask, current_app, g, jsonify, redirect, render_template, request, session, url_for
from werkzeug.exceptions import HTTPException
from werkzeug.security import check_password_hash, generate_password_hash

from priority import suggest_priority

BASE_DIR = Path(__file__).resolve().parent

STATUSES = ["To Do", "In Progress", "Completed"]
PRIORITIES = ["Low", "Medium", "High", "Urgent"]
ROLES = ["admin", "manager", "user"]
STAFF_ROLES = ("admin", "manager")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('admin', 'manager', 'user')),
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'To Do' CHECK (status IN ('To Do', 'In Progress', 'Completed')),
    priority TEXT NOT NULL DEFAULT 'Medium' CHECK (priority IN ('Low', 'Medium', 'High', 'Urgent')),
    assignee_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    creator_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    due_date TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tasks_assignee ON tasks(assignee_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
"""

TASK_SELECT = """
SELECT t.*, a.name AS assignee_name, a.email AS assignee_email, c.name AS creator_name
FROM tasks t
LEFT JOIN users a ON a.id = t.assignee_id
LEFT JOIN users c ON c.id = t.creator_id
"""


# --------------------------------------------------------------------------- helpers
def load_env_file(path=None):
    """Tiny .env reader (no extra dependency). Real environment variables win."""
    path = Path(path) if path else BASE_DIR / ".env"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def default_db_path():
    configured = os.environ.get("DATABASE_PATH")
    if configured:
        path = Path(configured)
        return str(path if path.is_absolute() else BASE_DIR / path)
    return str(BASE_DIR / "instance" / "taskflow.db")


def init_db(db_path):
    """Create the database file and tables if they do not exist (safe to repeat)."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def api_error(message, status, details=None):
    body = {"error": message}
    if details:
        body["details"] = details
    return jsonify(body), status


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            return api_error("Authentication required. Please log in.", 401)
        return view(*args, **kwargs)
    return wrapped


def roles_required(*roles):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if g.user["role"] not in roles:
                return api_error("You do not have permission to perform this action.", 403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


def json_body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else None


def is_staff(user):
    return user["role"] in STAFF_ROLES


def user_to_dict(row, include_role=True):
    data = {"id": row["id"], "name": row["name"], "email": row["email"]}
    if include_role:
        data["role"] = row["role"]
    return data


def task_to_dict(row, user):
    staff = is_staff(user)
    return {
        "id": row["id"],
        "title": row["title"],
        "description": row["description"],
        "status": row["status"],
        "priority": row["priority"],
        "assignee_id": row["assignee_id"],
        "assignee_name": row["assignee_name"],
        "assignee_email": row["assignee_email"],
        "due_date": row["due_date"],
        "creator_id": row["creator_id"],
        "creator_name": row["creator_name"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "permissions": {
            "edit": staff,
            "delete": staff,
            "update_status": staff or row["assignee_id"] == user["id"],
        },
    }


def visibility_clause(user):
    """Admins/managers see every task; users only see tasks assigned to them."""
    if is_staff(user):
        return "1=1", []
    return "t.assignee_id = ?", [user["id"]]


def fetch_task(task_id):
    return get_db().execute(TASK_SELECT + " WHERE t.id = ?", (task_id,)).fetchone()


def escape_like(value):
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def validate_task(data, partial=False):
    clean, errors = {}, {}

    if not partial or "title" in data:
        title = data.get("title")
        if not isinstance(title, str) or not title.strip():
            errors["title"] = "Title is required."
        elif len(title.strip()) > 120:
            errors["title"] = "Title must be 120 characters or fewer."
        else:
            clean["title"] = title.strip()

    if not partial or "description" in data:
        description = data.get("description") or ""
        if not isinstance(description, str):
            errors["description"] = "Description must be text."
        elif len(description) > 2000:
            errors["description"] = "Description must be 2000 characters or fewer."
        else:
            clean["description"] = description.strip()

    if not partial or "status" in data:
        status = data.get("status", "To Do")
        if status not in STATUSES:
            errors["status"] = "Status must be one of: " + ", ".join(STATUSES) + "."
        else:
            clean["status"] = status

    if not partial or "priority" in data:
        priority = data.get("priority", "Medium")
        if priority not in PRIORITIES:
            errors["priority"] = "Priority must be one of: " + ", ".join(PRIORITIES) + "."
        else:
            clean["priority"] = priority

    if not partial or "assignee_id" in data:
        raw = data.get("assignee_id")
        if raw in (None, ""):
            clean["assignee_id"] = None
        else:
            try:
                if isinstance(raw, bool):
                    raise ValueError
                assignee_id = int(raw)
            except (TypeError, ValueError):
                errors["assignee_id"] = "Assignee is invalid."
            else:
                exists = get_db().execute("SELECT 1 FROM users WHERE id = ?", (assignee_id,)).fetchone()
                if exists:
                    clean["assignee_id"] = assignee_id
                else:
                    errors["assignee_id"] = "Assignee does not exist."

    if not partial or "due_date" in data:
        raw = data.get("due_date")
        if raw in (None, ""):
            clean["due_date"] = None
        else:
            try:
                if not isinstance(raw, str) or len(raw) != 10:
                    raise ValueError
                clean["due_date"] = date.fromisoformat(raw).isoformat()
            except ValueError:
                errors["due_date"] = "Due date must be a valid date (YYYY-MM-DD)."

    return clean, errors


def validation_failed(errors):
    return api_error(next(iter(errors.values())), 400, errors)


# --------------------------------------------------------------------------- app factory
def create_app(test_config=None):
    load_env_file()
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-only-secret-change-me"),
        DATABASE=default_db_path(),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE") == "1",
        PERMANENT_SESSION_LIFETIME=timedelta(days=7),
    )
    if test_config:
        app.config.update(test_config)
    init_db(app.config["DATABASE"])
    logging.basicConfig(level=logging.INFO)

    @app.teardown_appcontext
    def close_db(_exc):
        db = g.pop("db", None)
        if db is not None:
            db.close()

    @app.before_request
    def load_user():
        g.user = None
        if request.endpoint == "static":
            return None
        user_id = session.get("user_id")
        if user_id is not None:
            row = get_db().execute(
                "SELECT id, name, email, role FROM users WHERE id = ?", (user_id,)
            ).fetchone()
            if row:
                g.user = row
            else:
                session.clear()
        return None

    @app.before_request
    def require_json_for_api_writes():
        if (request.path.startswith("/api/") and request.method in ("POST", "PUT", "PATCH")
                and request.content_length and not request.is_json):
            return api_error("Content-Type must be application/json.", 415)
        return None

    @app.after_request
    def api_headers(response):
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        return response

    # ----------------------------------------------------------------- error handlers
    @app.errorhandler(HTTPException)
    def handle_http_error(err):
        if request.path.startswith("/api/"):
            return api_error(err.description or err.name, err.code)
        return render_template("error.html", code=err.code, message=err.description), err.code

    @app.errorhandler(Exception)
    def handle_unexpected_error(err):
        app.logger.exception("Unhandled error: %s", err)
        if request.path.startswith("/api/"):
            return api_error("Something went wrong on the server. Please try again.", 500)
        return render_template("error.html", code=500, message="Something went wrong."), 500

    # ----------------------------------------------------------------- pages
    @app.get("/")
    def index():
        if g.user is None:
            return redirect(url_for("login_page"))
        return render_template("dashboard.html", user=user_to_dict(g.user),
                               statuses=STATUSES, priorities=PRIORITIES)

    @app.get("/login")
    def login_page():
        if g.user is not None:
            return redirect(url_for("index"))
        return render_template("login.html")

    @app.get("/register")
    def register_page():
        if g.user is not None:
            return redirect(url_for("index"))
        return render_template("register.html")

    # ----------------------------------------------------------------- auth API
    @app.post("/api/auth/register")
    def register():
        data = json_body()
        if data is None:
            return api_error("Request body must be a JSON object.", 400)
        errors = {}
        name = (data.get("name") or "").strip() if isinstance(data.get("name"), str) else ""
        email = (data.get("email") or "").strip().lower() if isinstance(data.get("email"), str) else ""
        password = data.get("password") if isinstance(data.get("password"), str) else ""
        if not 2 <= len(name) <= 60:
            errors["name"] = "Name must be between 2 and 60 characters."
        if not EMAIL_RE.match(email) or len(email) > 120:
            errors["email"] = "Please enter a valid email address."
        if len(password) < 8 or not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
            errors["password"] = "Password must be at least 8 characters and include a letter and a number."
        if errors:
            return validation_failed(errors)
        db = get_db()
        if db.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
            return api_error("An account with this email already exists.", 409,
                             {"email": "An account with this email already exists."})
        # The role is ALWAYS 'user' here; any role sent by the client is ignored.
        cursor = db.execute(
            "INSERT INTO users (name, email, password_hash, role, created_at) VALUES (?, ?, ?, 'user', ?)",
            (name, email, generate_password_hash(password), now_iso()),
        )
        db.commit()
        session.clear()
        session["user_id"] = cursor.lastrowid
        session.permanent = True
        user = db.execute("SELECT id, name, email, role FROM users WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return jsonify({"user": user_to_dict(user)}), 201

    @app.post("/api/auth/login")
    def login():
        data = json_body()
        if data is None:
            return api_error("Request body must be a JSON object.", 400)
        email = data.get("email").strip().lower() if isinstance(data.get("email"), str) else ""
        password = data.get("password") if isinstance(data.get("password"), str) else ""
        if not email or not password:
            return api_error("Email and password are required.", 400)
        row = get_db().execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if row is None or not check_password_hash(row["password_hash"], password):
            return api_error("Invalid email or password.", 401)
        session.clear()
        session["user_id"] = row["id"]
        session.permanent = True
        return jsonify({"user": user_to_dict(row)})

    @app.post("/api/auth/logout")
    def logout():
        session.clear()
        return jsonify({"message": "Logged out."})

    @app.get("/api/auth/me")
    @login_required
    def me():
        return jsonify({"user": user_to_dict(g.user)})

    # ----------------------------------------------------------------- users API
    @app.get("/api/users")
    @login_required
    def list_users():
        db = get_db()
        if g.user["role"] == "admin":
            rows = db.execute("SELECT id, name, email, role FROM users ORDER BY name COLLATE NOCASE").fetchall()
            return jsonify({"users": [user_to_dict(r) for r in rows]})
        if g.user["role"] == "manager":
            # Managers need the list to assign tasks, but not other people's roles.
            rows = db.execute("SELECT id, name, email, role FROM users ORDER BY name COLLATE NOCASE").fetchall()
            return jsonify({"users": [user_to_dict(r, include_role=False) for r in rows]})
        return jsonify({"users": [user_to_dict(g.user, include_role=False)]})

    @app.patch("/api/users/<int:user_id>")
    @roles_required("admin")
    def update_user(user_id):
        data = json_body()
        if data is None:
            return api_error("Request body must be a JSON object.", 400)
        db = get_db()
        target = db.execute("SELECT id, name, email, role FROM users WHERE id = ?", (user_id,)).fetchone()
        if target is None:
            return api_error("User not found.", 404)
        updates = {}
        if "role" in data:
            if data["role"] not in ROLES:
                return api_error("Role must be one of: " + ", ".join(ROLES) + ".", 400)
            if target["id"] == g.user["id"] and data["role"] != target["role"]:
                return api_error("You cannot change your own role.", 400)
            updates["role"] = data["role"]
        if "name" in data:
            name = data["name"].strip() if isinstance(data["name"], str) else ""
            if not 2 <= len(name) <= 60:
                return api_error("Name must be between 2 and 60 characters.", 400)
            updates["name"] = name
        if not updates:
            return api_error("Nothing to update.", 400)
        assignments = ", ".join(f"{col} = ?" for col in updates)
        db.execute(f"UPDATE users SET {assignments} WHERE id = ?", (*updates.values(), user_id))
        db.commit()
        row = db.execute("SELECT id, name, email, role FROM users WHERE id = ?", (user_id,)).fetchone()
        return jsonify({"user": user_to_dict(row)})

    @app.delete("/api/users/<int:user_id>")
    @roles_required("admin")
    def delete_user(user_id):
        if user_id == g.user["id"]:
            return api_error("You cannot delete your own account.", 400)
        db = get_db()
        if db.execute("SELECT 1 FROM users WHERE id = ?", (user_id,)).fetchone() is None:
            return api_error("User not found.", 404)
        db.execute("DELETE FROM users WHERE id = ?", (user_id,))  # tasks keep existing, assignee becomes NULL
        db.commit()
        return jsonify({"message": "User deleted."})

    # ----------------------------------------------------------------- tasks API
    @app.get("/api/tasks")
    @login_required
    def list_tasks():
        where, params = [], []
        scope, scope_params = visibility_clause(g.user)
        where.append(scope)
        params.extend(scope_params)

        q = request.args.get("q", "").strip()
        if q:
            where.append("t.title LIKE ? ESCAPE '\\'")
            params.append(f"%{escape_like(q)}%")

        status = request.args.get("status", "").strip()
        if status and status.lower() != "all":
            if status not in STATUSES:
                return api_error("Invalid status filter.", 400)
            where.append("t.status = ?")
            params.append(status)

        priority = request.args.get("priority", "").strip()
        if priority and priority.lower() != "all":
            if priority not in PRIORITIES:
                return api_error("Invalid priority filter.", 400)
            where.append("t.priority = ?")
            params.append(priority)

        assignee = request.args.get("assignee", "").strip()
        if assignee and assignee.lower() != "all":
            if assignee == "unassigned":
                where.append("t.assignee_id IS NULL")
            elif assignee.isdigit():
                where.append("t.assignee_id = ?")
                params.append(int(assignee))
            else:
                return api_error("Invalid assignee filter.", 400)

        sql = (TASK_SELECT + " WHERE " + " AND ".join(where) +
               " ORDER BY (t.status = 'Completed'),"
               " CASE t.priority WHEN 'Urgent' THEN 0 WHEN 'High' THEN 1 WHEN 'Medium' THEN 2 ELSE 3 END,"
               " COALESCE(t.due_date, '9999-12-31'), t.id DESC")
        rows = get_db().execute(sql, params).fetchall()
        tasks = [task_to_dict(r, g.user) for r in rows]
        return jsonify({"tasks": tasks, "count": len(tasks)})

    @app.get("/api/tasks/stats")
    @login_required
    def task_stats():
        scope, params = visibility_clause(g.user)
        row = get_db().execute(
            "SELECT COUNT(*) AS total,"
            " SUM(t.status = 'To Do') AS pending,"
            " SUM(t.status = 'In Progress') AS in_progress,"
            " SUM(t.status = 'Completed') AS completed,"
            " SUM(t.priority = 'Urgent' AND t.status != 'Completed') AS urgent"
            f" FROM tasks t WHERE {scope}", params).fetchone()
        return jsonify({key: row[key] or 0 for key in ("total", "pending", "in_progress", "completed", "urgent")})

    @app.post("/api/tasks")
    @roles_required(*STAFF_ROLES)
    def create_task():
        data = json_body()
        if data is None:
            return api_error("Request body must be a JSON object.", 400)
        clean, errors = validate_task(data)
        if errors:
            return validation_failed(errors)
        db = get_db()
        timestamp = now_iso()
        cursor = db.execute(
            "INSERT INTO tasks (title, description, status, priority, assignee_id, creator_id, due_date,"
            " created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (clean["title"], clean["description"], clean["status"], clean["priority"],
             clean["assignee_id"], g.user["id"], clean["due_date"], timestamp, timestamp),
        )
        db.commit()
        return jsonify({"task": task_to_dict(fetch_task(cursor.lastrowid), g.user)}), 201

    @app.get("/api/tasks/<int:task_id>")
    @login_required
    def get_task(task_id):
        row = fetch_task(task_id)
        if row is None:
            return api_error("Task not found.", 404)
        if not is_staff(g.user) and row["assignee_id"] != g.user["id"]:
            return api_error("You do not have access to this task.", 403)
        return jsonify({"task": task_to_dict(row, g.user)})

    @app.route("/api/tasks/<int:task_id>", methods=["PUT", "PATCH"])
    @login_required
    def update_task(task_id):
        row = fetch_task(task_id)
        if row is None:
            return api_error("Task not found.", 404)
        data = json_body()
        if data is None:
            return api_error("Request body must be a JSON object.", 400)
        if not is_staff(g.user):
            if row["assignee_id"] != g.user["id"]:
                return api_error("You can only update tasks assigned to you.", 403)
            if set(data) - {"status"}:
                return api_error("Users can only update the status of their assigned tasks.", 403)
        clean, errors = validate_task(data, partial=True)
        if errors:
            return validation_failed(errors)
        if not clean:
            return api_error("Nothing to update.", 400)
        clean["updated_at"] = now_iso()
        assignments = ", ".join(f"{col} = ?" for col in clean)
        db = get_db()
        db.execute(f"UPDATE tasks SET {assignments} WHERE id = ?", (*clean.values(), task_id))
        db.commit()
        return jsonify({"task": task_to_dict(fetch_task(task_id), g.user)})

    @app.delete("/api/tasks/<int:task_id>")
    @roles_required(*STAFF_ROLES)
    def delete_task(task_id):
        db = get_db()
        if db.execute("SELECT 1 FROM tasks WHERE id = ?", (task_id,)).fetchone() is None:
            return api_error("Task not found.", 404)
        db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        db.commit()
        return jsonify({"message": "Task deleted."})

    # ----------------------------------------------------------------- AI Assist
    @app.post("/api/ai/suggest-priority")
    @login_required
    def ai_suggest_priority():
        data = json_body()
        if data is None:
            return api_error("Request body must be a JSON object.", 400)
        parts = [data.get(k) for k in ("text", "title", "description")]
        text = " ".join(p.strip() for p in parts if isinstance(p, str) and p.strip())
        if not text:
            return api_error("Please describe the task so a priority can be suggested.", 400,
                             {"text": "Please describe the task so a priority can be suggested."})
        if len(text) > 4000:
            return api_error("Description is too long (4000 characters maximum).", 400)
        due = data.get("due_date")
        return jsonify(suggest_priority(text, due if isinstance(due, str) else None))

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=5000, debug=os.environ.get("FLASK_DEBUG") == "1")
