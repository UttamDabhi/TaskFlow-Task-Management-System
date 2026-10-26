from tests.base import TaskFlowTestCase


class AuthorizationTests(TaskFlowTestCase):
    def test_user_cannot_create_or_delete_tasks(self):
        user = self.client_for("user")
        self.assertEqual(self.new_task(user).status_code, 403)
        self.assertEqual(user.delete("/api/tasks/1").status_code, 403)

    def test_user_only_sees_assigned_tasks(self):
        user = self.client_for("user")
        user_id = user.get("/api/auth/me").get_json()["user"]["id"]
        tasks = user.get("/api/tasks").get_json()["tasks"]
        self.assertGreater(len(tasks), 0)
        self.assertTrue(all(t["assignee_id"] == user_id for t in tasks))
        admin_total = self.client_for("admin").get("/api/tasks").get_json()["count"]
        self.assertLess(len(tasks), admin_total)
        self.assertEqual(user.get("/api/tasks/stats").get_json()["total"], len(tasks))

    def test_user_cannot_open_or_update_other_users_tasks(self):
        manager_task = next(t for t in self.client_for("admin").get("/api/tasks").get_json()["tasks"]
                            if t["assignee_name"] == "Manager User")
        user = self.client_for("user")
        self.assertEqual(user.get(f"/api/tasks/{manager_task['id']}").status_code, 403)
        self.assertEqual(user.patch(f"/api/tasks/{manager_task['id']}", json={"status": "Completed"}).status_code, 403)

    def test_user_can_update_status_of_own_task_only_status(self):
        user = self.client_for("user")
        task = user.get("/api/tasks").get_json()["tasks"][0]
        self.assertTrue(task["permissions"]["update_status"])
        self.assertFalse(task["permissions"]["edit"])
        ok = user.patch(f"/api/tasks/{task['id']}", json={"status": "Completed"})
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.get_json()["task"]["status"], "Completed")
        for forbidden in ({"title": "Hacked"}, {"priority": "Low"}, {"assignee_id": None}, {"status": "To Do", "title": "x"}):
            self.assertEqual(user.patch(f"/api/tasks/{task['id']}", json=forbidden).status_code, 403, forbidden)

    def test_user_list_is_limited_and_hides_roles(self):
        users = self.client_for("user").get("/api/users").get_json()["users"]
        self.assertEqual(len(users), 1)
        self.assertNotIn("role", users[0])

    def test_manager_can_manage_tasks_and_assign(self):
        manager = self.client_for("manager")
        assignee = self.user_id("user")
        created = self.new_task(manager, title="Manager task", assignee_id=assignee)
        self.assertEqual(created.status_code, 201)
        task = created.get_json()["task"]
        self.assertEqual(task["assignee_id"], assignee)
        self.assertEqual(manager.patch(f"/api/tasks/{task['id']}", json={"priority": "High"}).status_code, 200)
        self.assertEqual(manager.delete(f"/api/tasks/{task['id']}").status_code, 200)

    def test_manager_cannot_manage_users(self):
        manager = self.client_for("manager")
        target = self.user_id("user")
        self.assertEqual(manager.patch(f"/api/users/{target}", json={"role": "admin"}).status_code, 403)
        self.assertEqual(manager.delete(f"/api/users/{target}").status_code, 403)
        users = manager.get("/api/users").get_json()["users"]
        self.assertGreaterEqual(len(users), 3)
        self.assertNotIn("role", users[0])

    def test_unauthenticated_cannot_use_any_protected_endpoint(self):
        for method, path in [("get", "/api/tasks"), ("post", "/api/tasks"), ("get", "/api/tasks/1"),
                             ("patch", "/api/tasks/1"), ("delete", "/api/tasks/1"), ("get", "/api/tasks/stats"),
                             ("get", "/api/users"), ("patch", "/api/users/1"), ("delete", "/api/users/1"),
                             ("post", "/api/ai/suggest-priority")]:
            response = getattr(self.client, method)(path, json={}) if method != "get" else self.client.get(path)
            self.assertEqual(response.status_code, 401, (method, path))

    def test_admin_can_change_roles_and_delete_users(self):
        admin = self.client_for("admin")
        target = self.user_id("user")
        response = admin.patch(f"/api/users/{target}", json={"role": "manager"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["user"]["role"], "manager")
        self.assertEqual(admin.patch(f"/api/users/{target}", json={"role": "superuser"}).status_code, 400)
        self.assertEqual(admin.delete(f"/api/users/{target}").status_code, 200)
        self.assertEqual(admin.delete(f"/api/users/{target}").status_code, 404)
        # their tasks survive, now unassigned
        tasks = admin.get("/api/tasks").get_json()["tasks"]
        self.assertTrue(any(t["assignee_id"] is None for t in tasks))

    def test_admin_cannot_demote_or_delete_self(self):
        admin = self.client_for("admin")
        me = admin.get("/api/auth/me").get_json()["user"]["id"]
        self.assertEqual(admin.patch(f"/api/users/{me}", json={"role": "user"}).status_code, 400)
        self.assertEqual(admin.delete(f"/api/users/{me}").status_code, 400)

    def test_role_change_takes_effect_on_next_request(self):
        user = self.client_for("user")
        self.assertEqual(self.new_task(user).status_code, 403)
        self.client_for("admin").patch(f"/api/users/{self.user_id('user')}", json={"role": "manager"})
        self.assertEqual(self.new_task(user).status_code, 201)
