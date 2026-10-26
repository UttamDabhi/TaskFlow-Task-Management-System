from tests.base import TaskFlowTestCase, CREDENTIALS


class AuthTests(TaskFlowTestCase):
    def test_unauthenticated_api_returns_json_401(self):
        response = self.client.get("/api/tasks")
        self.assertEqual(response.status_code, 401)
        self.assertTrue(response.is_json)
        self.assertIn("Authentication required", response.get_json()["error"])

    def test_unauthenticated_home_redirects_to_login(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/login"))

    def test_login_and_register_pages_render(self):
        for path in ("/login", "/register"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertIn(b"TaskFlow", response.data)

    def test_login_success_sets_session_cookie_and_allows_api(self):
        email, password = CREDENTIALS["admin"]
        response = self.client.post("/api/auth/login", json={"email": email, "password": password})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["user"]["role"], "admin")
        cookie = response.headers.get("Set-Cookie", "")
        self.assertIn("session=", cookie)
        self.assertIn("HttpOnly", cookie)
        self.assertEqual(self.client.get("/api/tasks").status_code, 200)
        self.assertEqual(self.client.get("/").status_code, 200)

    def test_login_email_is_case_insensitive(self):
        response = self.client.post("/api/auth/login", json={"email": " ADMIN@example.com ", "password": "Admin123!"})
        self.assertEqual(response.status_code, 200)

    def test_login_wrong_password_and_unknown_user(self):
        bad = self.client.post("/api/auth/login", json={"email": "admin@example.com", "password": "nope"})
        self.assertEqual(bad.status_code, 401)
        self.assertEqual(bad.get_json()["error"], "Invalid email or password.")
        unknown = self.client.post("/api/auth/login", json={"email": "ghost@example.com", "password": "x"})
        self.assertEqual(unknown.status_code, 401)
        self.assertEqual(self.client.get("/api/tasks").status_code, 401)

    def test_login_missing_fields_and_bad_body(self):
        self.assertEqual(self.client.post("/api/auth/login", json={"email": "", "password": ""}).status_code, 400)
        response = self.client.post("/api/auth/login", data="email=a", content_type="text/plain")
        self.assertEqual(response.status_code, 415)
        self.assertTrue(response.is_json)

    def test_logout_clears_session(self):
        client = self.client_for("user")
        self.assertEqual(client.get("/api/auth/me").status_code, 200)
        self.assertEqual(client.post("/api/auth/logout").status_code, 200)
        self.assertEqual(client.get("/api/auth/me").status_code, 401)

    def test_register_creates_user_role_and_logs_in(self):
        response = self.client.post("/api/auth/register", json={
            "name": "New Person", "email": "New@Example.com", "password": "Passw0rdX"})
        self.assertEqual(response.status_code, 201)
        user = response.get_json()["user"]
        self.assertEqual(user["role"], "user")
        self.assertEqual(user["email"], "new@example.com")
        self.assertEqual(self.client.get("/api/auth/me").get_json()["user"]["email"], "new@example.com")

    def test_register_cannot_choose_admin_role(self):
        response = self.client.post("/api/auth/register", json={
            "name": "Sneaky", "email": "sneaky@example.com", "password": "Passw0rdX", "role": "admin"})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["user"]["role"], "user")
        self.assertEqual(self.client.get("/api/users").get_json()["users"][0].get("role"), None)

    def test_register_validation(self):
        base = {"name": "Valid Name", "email": "valid@example.com", "password": "Passw0rdX"}
        cases = {
            "name": {**base, "name": "A"},
            "email": {**base, "email": "not-an-email"},
            "password": {**base, "password": "short1"},
        }
        for field, payload in cases.items():
            response = self.client.post("/api/auth/register", json=payload)
            self.assertEqual(response.status_code, 400, field)
            self.assertIn(field, response.get_json()["details"])
        self.assertEqual(self.client.post("/api/auth/register", json={**base, "password": "onlyletters"}).status_code, 400)

    def test_register_duplicate_email(self):
        response = self.client.post("/api/auth/register", json={
            "name": "Dup", "email": "admin@example.com", "password": "Passw0rdX"})
        self.assertEqual(response.status_code, 409)

    def test_passwords_are_hashed(self):
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        hashes = [r[0] for r in conn.execute("SELECT password_hash FROM users")]
        conn.close()
        self.assertTrue(hashes)
        for value in hashes:
            for plain in ("Admin123!", "Manager123!", "User12345!"):
                self.assertNotIn(plain, value)
            self.assertTrue(value.startswith(("scrypt:", "pbkdf2:")))

    def test_api_404_and_405_are_json(self):
        client = self.client_for("user")
        self.assertTrue(client.get("/api/nope").is_json)
        self.assertEqual(client.get("/api/nope").status_code, 404)
        response = client.delete("/api/auth/login")
        self.assertEqual(response.status_code, 405)
        self.assertTrue(response.is_json)
