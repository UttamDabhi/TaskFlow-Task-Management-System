from tests.base import TaskFlowTestCase


class TaskCrudTests(TaskFlowTestCase):
    def setUp(self):
        super().setUp()
        self.manager = self.client_for("manager")

    def test_create_read_update_delete(self):
        assignee = self.user_id("user")
        created = self.new_task(self.manager, title="  Build report  ", description="Quarterly",
                                priority="High", assignee_id=assignee, due_date="2030-01-15")
        self.assertEqual(created.status_code, 201)
        task = created.get_json()["task"]
        self.assertEqual(task["title"], "Build report")
        self.assertEqual(task["creator_name"], "Manager User")
        self.assertEqual(task["assignee_name"], "Demo User")
        self.assertTrue(task["created_at"] and task["updated_at"])

        fetched = self.manager.get(f"/api/tasks/{task['id']}")
        self.assertEqual(fetched.get_json()["task"]["due_date"], "2030-01-15")

        updated = self.manager.put(f"/api/tasks/{task['id']}", json={"title": "Renamed", "status": "In Progress", "assignee_id": None})
        self.assertEqual(updated.status_code, 200)
        body = updated.get_json()["task"]
        self.assertEqual((body["title"], body["status"], body["assignee_id"]), ("Renamed", "In Progress", None))
        self.assertEqual(body["priority"], "High")  # untouched fields are preserved

        self.assertEqual(self.manager.delete(f"/api/tasks/{task['id']}").status_code, 200)
        self.assertEqual(self.manager.get(f"/api/tasks/{task['id']}").status_code, 404)

    def test_defaults_on_create(self):
        task = self.manager.post("/api/tasks", json={"title": "Only title"}).get_json()["task"]
        self.assertEqual((task["status"], task["priority"], task["assignee_id"]), ("To Do", "Medium", None))

    def test_validation_errors(self):
        bad_payloads = [
            ({"title": ""}, "title"), ({"title": "x" * 121}, "title"),
            ({"title": "ok", "status": "Done"}, "status"), ({"title": "ok", "priority": "Critical"}, "priority"),
            ({"title": "ok", "assignee_id": 9999}, "assignee_id"), ({"title": "ok", "assignee_id": "abc"}, "assignee_id"),
            ({"title": "ok", "due_date": "31/12/2030"}, "due_date"), ({"title": "ok", "due_date": "2030-02-31"}, "due_date"),
        ]
        for payload, field in bad_payloads:
            response = self.manager.post("/api/tasks", json=payload)
            self.assertEqual(response.status_code, 400, payload)
            self.assertIn(field, response.get_json()["details"])
        self.assertEqual(self.manager.post("/api/tasks", json=["not", "an", "object"]).status_code, 400)
        task_id = self.new_task(self.manager).get_json()["task"]["id"]
        self.assertEqual(self.manager.patch(f"/api/tasks/{task_id}", json={}).status_code, 400)
        self.assertEqual(self.manager.patch(f"/api/tasks/{task_id}", json={"status": "bogus"}).status_code, 400)

    def test_missing_task_returns_404(self):
        self.assertEqual(self.manager.get("/api/tasks/99999").status_code, 404)
        self.assertEqual(self.manager.patch("/api/tasks/99999", json={"status": "To Do"}).status_code, 404)
        self.assertEqual(self.manager.delete("/api/tasks/99999").status_code, 404)

    def test_html_is_stored_as_text_not_executed(self):
        task = self.new_task(self.manager, title="<script>alert(1)</script>").get_json()["task"]
        self.assertEqual(task["title"], "<script>alert(1)</script>")  # escaped by the frontend (esc())


class TaskFilterTests(TaskFlowTestCase):
    def setUp(self):
        super().setUp()
        self.admin = self.client_for("admin")

    def titles(self, query=""):
        response = self.admin.get("/api/tasks" + query)
        self.assertEqual(response.status_code, 200)
        return [t["title"] for t in response.get_json()["tasks"]]

    def test_list_returns_seeded_tasks(self):
        self.assertEqual(len(self.titles()), 8)

    def test_search_by_title_case_insensitive(self):
        self.assertEqual(self.titles("?q=OUTAGE"), ["Fix production login outage"])
        self.assertEqual(self.titles("?q=zzz-nothing"), [])

    def test_search_treats_wildcards_literally(self):
        self.assertEqual(self.titles("?q=%25"), [])
        self.assertEqual(self.titles("?q=_"), [])

    def test_filter_by_status_priority_assignee(self):
        statuses = {t["status"] for t in self.admin.get("/api/tasks?status=Completed").get_json()["tasks"]}
        self.assertEqual(statuses, {"Completed"})
        priorities = {t["priority"] for t in self.admin.get("/api/tasks?priority=Urgent").get_json()["tasks"]}
        self.assertEqual(priorities, {"Urgent"})
        unassigned = self.admin.get("/api/tasks?assignee=unassigned").get_json()["tasks"]
        self.assertEqual(len(unassigned), 1)
        uid = self.user_id("user")
        mine = self.admin.get(f"/api/tasks?assignee={uid}").get_json()["tasks"]
        self.assertTrue(mine and all(t["assignee_id"] == uid for t in mine))

    def test_combined_filters(self):
        uid = self.user_id("user")
        result = self.admin.get(f"/api/tasks?assignee={uid}&status=To%20Do&priority=Low").get_json()["tasks"]
        self.assertEqual([t["title"] for t in result], ["Write API documentation for task endpoints"])
        self.assertEqual(self.admin.get("/api/tasks?status=All&priority=&assignee=all").get_json()["count"], 8)

    def test_invalid_filters_return_400(self):
        for query in ("?status=bogus", "?priority=bogus", "?assignee=abc"):
            self.assertEqual(self.admin.get("/api/tasks" + query).status_code, 400, query)

    def test_default_ordering_puts_completed_last_and_urgent_first(self):
        tasks = self.admin.get("/api/tasks").get_json()["tasks"]
        self.assertEqual(tasks[0]["priority"], "Urgent")
        self.assertEqual({t["status"] for t in tasks[-2:]}, {"Completed"})

    def test_dashboard_stats(self):
        stats = self.admin.get("/api/tasks/stats").get_json()
        self.assertEqual(stats, {"total": 8, "pending": 4, "in_progress": 2, "completed": 2, "urgent": 1})
