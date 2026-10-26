"""Shared test helpers: every test gets its own temporary database."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402
from seed import seed_database  # noqa: E402

CREDENTIALS = {
    "admin": ("admin@example.com", "Admin123!"),
    "manager": ("manager@example.com", "Manager123!"),
    "user": ("user@example.com", "User12345!"),
}


class TaskFlowTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self._tmp.name, "test.db")
        seed_database(self.db_path)
        self.app = create_app({"TESTING": True, "DATABASE": self.db_path, "SECRET_KEY": "test-secret"})
        self.client = self.app.test_client()

    def tearDown(self):
        self._tmp.cleanup()

    def client_for(self, role):
        client = self.app.test_client()
        email, password = CREDENTIALS[role]
        response = client.post("/api/auth/login", json={"email": email, "password": password})
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        return client

    def user_id(self, role):
        return self.client_for(role).get("/api/auth/me").get_json()["user"]["id"]

    def new_task(self, client, **overrides):
        payload = {"title": "Test task", "description": "desc", "status": "To Do", "priority": "Medium"}
        payload.update(overrides)
        return client.post("/api/tasks", json=payload)
