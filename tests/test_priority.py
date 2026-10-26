from datetime import date

from priority import suggest_priority
from tests.base import TaskFlowTestCase


class PriorityEngineTests(TaskFlowTestCase):
    def test_outage_is_urgent(self):
        result = suggest_priority("Production outage affecting all users; fix ASAP")
        self.assertEqual(result["priority"], "Urgent")
        self.assertIn("outage", result["signals"])
        self.assertEqual(result["method"], "rule-based")
        self.assertIn("not an AI language model", result["disclaimer"])

    def test_customer_bug_is_high(self):
        self.assertEqual(suggest_priority("Fix login bug reported by a customer")["priority"], "High")

    def test_plain_task_is_medium(self):
        result = suggest_priority("Write unit tests for the report module")
        self.assertEqual(result["priority"], "Medium")
        self.assertEqual(result["signals"], [])

    def test_minor_work_is_low(self):
        self.assertEqual(suggest_priority("Fix typo in documentation")["priority"], "Low")
        self.assertEqual(suggest_priority("Nice to have: refactor helper functions")["priority"], "Low")

    def test_negated_urgency_is_not_urgent(self):
        self.assertEqual(suggest_priority("This is not urgent, no rush")["priority"], "Low")
        self.assertNotEqual(suggest_priority("Reorganise files, not urgent")["priority"], "Urgent")

    def test_due_date_raises_priority(self):
        today = date(2026, 10, 26)
        base = "Prepare the monthly summary"
        self.assertEqual(suggest_priority(base, today=today)["priority"], "Medium")
        self.assertEqual(suggest_priority(base, "2026-10-27", today=today)["priority"], "High")
        self.assertEqual(suggest_priority(base, "2026-10-20", today=today)["priority"], "High")
        self.assertEqual(suggest_priority(base, "bad-date", today=today)["priority"], "Medium")

    def test_empty_text_defaults_to_medium(self):
        self.assertEqual(suggest_priority("")["priority"], "Medium")


class PriorityEndpointTests(TaskFlowTestCase):
    def test_endpoint_works_for_every_role(self):
        for role in ("admin", "manager", "user"):
            client = self.client_for(role)
            response = client.post("/api/ai/suggest-priority", json={"text": "Production outage affecting all users; fix ASAP"})
            self.assertEqual(response.status_code, 200, role)
            body = response.get_json()
            self.assertEqual(body["priority"], "Urgent")
            self.assertTrue(body["explanation"])

    def test_title_description_and_due_date_are_combined(self):
        client = self.client_for("manager")
        response = client.post("/api/ai/suggest-priority", json={"title": "Fix checkout error", "description": "customers cannot pay"})
        self.assertEqual(response.get_json()["priority"], "High")

    def test_empty_input_returns_400(self):
        client = self.client_for("user")
        self.assertEqual(client.post("/api/ai/suggest-priority", json={"text": "   "}).status_code, 400)
        self.assertEqual(client.post("/api/ai/suggest-priority", json={}).status_code, 400)

    def test_requires_login(self):
        self.assertEqual(self.client.post("/api/ai/suggest-priority", json={"text": "x"}).status_code, 401)


class SeedTests(TaskFlowTestCase):
    def test_seed_is_idempotent_and_keeps_changed_passwords(self):
        import sqlite3
        from seed import seed_database
        admin = self.client_for("admin")
        before = admin.get("/api/tasks").get_json()["count"]
        conn = sqlite3.connect(self.db_path)
        conn.execute("UPDATE users SET password_hash = 'custom-hash', name = 'Renamed' WHERE email = 'admin@example.com'")
        conn.commit()
        conn.close()
        for _ in range(3):
            summary = seed_database(self.db_path)
            self.assertEqual(summary["users_created"], 0)
            self.assertEqual(summary["tasks_created"], 0)
        conn = sqlite3.connect(self.db_path)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM users").fetchone()[0], 3)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0], before)
        self.assertEqual(conn.execute("SELECT password_hash, name FROM users WHERE email='admin@example.com'").fetchone(),
                         ("custom-hash", "Renamed"))
        conn.close()
