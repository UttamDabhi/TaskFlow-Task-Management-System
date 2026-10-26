/* TaskFlow dashboard. */
(function () {
  "use strict";
  const { api, esc, toast } = TF;

  const me = JSON.parse(document.getElementById("boot").textContent);
  const isStaff = me.role === "admin" || me.role === "manager";
  const STATUSES = ["To Do", "In Progress", "Completed"];
  const $ = function (id) { return document.getElementById(id); };

  const state = { users: [], tasks: [], editingId: null };
  const titles = { tasks: "Tasks", ai: "AI Assist", users: "Users" };

  /* ---------- navigation ---------- */
  function showView(name) {
    document.querySelectorAll(".view").forEach(function (v) { v.hidden = v.id !== "view-" + name; });
    document.querySelectorAll(".nav-item").forEach(function (b) {
      b.classList.toggle("active", b.dataset.view === name);
    });
    $("view-title").textContent = titles[name];
    const newBtn = $("new-task-btn");
    if (newBtn) { newBtn.hidden = name !== "tasks"; }
    $("refresh-btn").hidden = name === "ai";
    closeSidebar();
    if (name === "users") { loadUsersTable(); }
  }
  function closeSidebar() { $("sidebar").classList.remove("open"); $("scrim").hidden = true; }
  document.querySelectorAll(".nav-item").forEach(function (b) {
    b.addEventListener("click", function () { showView(b.dataset.view); });
  });
  $("menu-btn").addEventListener("click", function () {
    $("sidebar").classList.add("open"); $("scrim").hidden = false;
  });
  $("scrim").addEventListener("click", closeSidebar);

  $("logout-btn").addEventListener("click", async function () {
    try { await api("/api/auth/logout", { method: "POST", noRedirect: true }); } catch (e) { /* ignore */ }
    window.location.href = "/login";
  });

  /* ---------- formatting ---------- */
  function fmtDate(iso) {
    if (!iso) { return "No due date"; }
    const d = new Date(iso + "T00:00:00");
    return d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
  }
  function isOverdue(task) {
    if (!task.due_date || task.status === "Completed") { return false; }
    const today = new Date(); today.setHours(0, 0, 0, 0);
    return new Date(task.due_date + "T00:00:00") < today;
  }
  function fmtStamp(iso) {
    return iso ? new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }) : "";
  }

  /* ---------- users (for assignee dropdowns) ---------- */
  async function loadUsers() {
    const data = await api("/api/users");
    state.users = data.users;
    const filter = $("filter-assignee");
    const keep = filter.value;
    filter.innerHTML = '<option value="">All assignees</option><option value="unassigned">Unassigned</option>' +
      state.users.map(function (u) { return '<option value="' + u.id + '">' + esc(u.name) + "</option>"; }).join("");
    filter.value = keep;
    $("f-assignee").innerHTML = '<option value="">Unassigned</option>' +
      state.users.map(function (u) { return '<option value="' + u.id + '">' + esc(u.name) + "</option>"; }).join("");
  }

  /* ---------- stats ---------- */
  async function loadStats() {
    const s = await api("/api/tasks/stats");
    ["total", "pending", "in_progress", "completed", "urgent"].forEach(function (k) {
      $("stat-" + k).textContent = s[k];
    });
  }

  /* ---------- tasks ---------- */
  function currentFilters() {
    const params = new URLSearchParams();
    const q = $("search").value.trim();
    if (q) { params.set("q", q); }
    [["status", "filter-status"], ["priority", "filter-priority"], ["assignee", "filter-assignee"]].forEach(function (p) {
      const v = $(p[1]).value;
      if (v) { params.set(p[0], v); }
    });
    return params;
  }
  function filtersActive() { return currentFilters().toString() !== ""; }

  async function loadTasks() {
    const box = $("task-state");
    box.className = "state";
    box.innerHTML = '<span class="spinner"></span>Loading tasks...';
    try {
      const qs = currentFilters().toString();
      const data = await api("/api/tasks" + (qs ? "?" + qs : ""));
      state.tasks = data.tasks;
      renderTasks();
    } catch (err) {
      state.tasks = [];
      $("task-list").innerHTML = "";
      box.className = "state error";
      box.innerHTML = "<p>" + esc(err.message) + '</p><button class="btn btn-ghost" id="retry-btn" type="button">Try again</button>';
      $("retry-btn").addEventListener("click", loadTasks);
    }
  }

  function renderTasks() {
    const box = $("task-state");
    const list = $("task-list");
    if (!state.tasks.length) {
      list.innerHTML = "";
      box.className = "state";
      if (filtersActive()) {
        box.textContent = "No tasks match your search or filters.";
      } else if (isStaff) {
        box.textContent = "No tasks yet. Click \u201C+ New task\u201D to create your first one.";
      } else {
        box.textContent = "No tasks are assigned to you right now.";
      }
      return;
    }
    box.className = "state"; box.textContent = "";
    list.innerHTML = state.tasks.map(taskCard).join("");
  }

  function taskCard(t) {
    const perms = t.permissions;
    const statusControl = perms.update_status
      ? '<select class="status-select" data-id="' + t.id + '" aria-label="Status for ' + esc(t.title) + '">' +
        STATUSES.map(function (s) { return "<option" + (s === t.status ? " selected" : "") + ">" + s + "</option>"; }).join("") + "</select>"
      : '<span class="badge">' + esc(t.status) + "</span>";
    const actions = perms.edit
      ? '<button class="btn btn-ghost btn-sm" data-action="edit" data-id="' + t.id + '" type="button">Edit</button>' +
        '<button class="btn btn-ghost btn-sm btn-danger" data-action="delete" data-id="' + t.id + '" type="button">Delete</button>'
      : "";
    return '<article class="task-card p-' + esc(t.priority) + (t.status === "Completed" ? " done" : "") + '">' +
      '<div class="task-head"><span class="task-title">' + esc(t.title) + "</span>" +
      '<span class="badge b-' + esc(t.priority) + '">' + esc(t.priority) + "</span></div>" +
      (t.description ? '<p class="task-desc">' + esc(t.description) + "</p>" : "") +
      '<div class="task-meta"><span>Assignee: ' + (t.assignee_name ? esc(t.assignee_name) : "Unassigned") + "</span>" +
      '<span class="' + (isOverdue(t) ? "overdue" : "") + '">' + (isOverdue(t) ? "Overdue: " : "Due: ") + fmtDate(t.due_date) + "</span>" +
      "<span>Created by " + esc(t.creator_name || "unknown") + "</span>" +
      '<span title="Created ' + esc(fmtStamp(t.created_at)) + '">Updated ' + esc(fmtStamp(t.updated_at)) + "</span></div>" +
      '<div class="task-foot">' + statusControl + actions + "</div></article>";
  }

  async function refreshAll(showToast) {
    try {
      await Promise.all([loadStats(), loadTasks()]);
      if (showToast) { toast("Refreshed."); }
    } catch (err) { toast(err.message, "error"); }
  }

  $("task-list").addEventListener("change", async function (e) {
    if (!e.target.classList.contains("status-select")) { return; }
    const id = e.target.dataset.id;
    e.target.disabled = true;
    try {
      await api("/api/tasks/" + id, { method: "PATCH", body: { status: e.target.value } });
      toast("Status updated.");
      await refreshAll();
    } catch (err) {
      toast(err.message, "error");
      await refreshAll();
    }
  });

  $("task-list").addEventListener("click", async function (e) {
    const btn = e.target.closest("button[data-action]");
    if (!btn) { return; }
    const id = Number(btn.dataset.id);
    if (btn.dataset.action === "edit") {
      openDialog(state.tasks.find(function (t) { return t.id === id; }));
    } else if (btn.dataset.action === "delete") {
      const task = state.tasks.find(function (t) { return t.id === id; });
      if (!window.confirm('Delete "' + (task ? task.title : "this task") + '"? This cannot be undone.')) { return; }
      try {
        await api("/api/tasks/" + id, { method: "DELETE" });
        toast("Task deleted.");
        await refreshAll();
      } catch (err) { toast(err.message, "error"); await refreshAll(); }
    }
  });

  /* ---------- filters ---------- */
  let searchTimer = null;
  $("search").addEventListener("input", function () {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(loadTasks, 300);
  });
  ["filter-status", "filter-priority", "filter-assignee"].forEach(function (id) {
    $(id).addEventListener("change", loadTasks);
  });
  $("clear-filters").addEventListener("click", function () {
    $("search").value = "";
    ["filter-status", "filter-priority", "filter-assignee"].forEach(function (id) { $(id).value = ""; });
    loadTasks();
  });
  $("refresh-btn").addEventListener("click", function () {
    const active = document.querySelector(".nav-item.active").dataset.view;
    if (active === "users") { loadUsersTable(); } else { refreshAll(true); }
  });

  /* ---------- create / edit dialog ---------- */
  const dialog = $("task-dialog");
  function openDialog(task) {
    state.editingId = task ? task.id : null;
    $("dialog-title").textContent = task ? "Edit task" : "New task";
    $("task-form-error").hidden = true;
    $("f-suggest-hint").textContent = "";
    $("f-title").value = task ? task.title : "";
    $("f-description").value = task ? task.description : "";
    $("f-status").value = task ? task.status : "To Do";
    $("f-priority").value = task ? task.priority : "Medium";
    $("f-assignee").value = task && task.assignee_id ? String(task.assignee_id) : "";
    $("f-due").value = task && task.due_date ? task.due_date : "";
    dialog.showModal();
    $("f-title").focus();
  }
  if ($("new-task-btn")) { $("new-task-btn").addEventListener("click", function () { openDialog(null); }); }
  $("dialog-cancel").addEventListener("click", function () { dialog.close(); });

  $("task-form").addEventListener("submit", async function (e) {
    e.preventDefault();
    const errBox = $("task-form-error");
    errBox.hidden = true;
    const body = {
      title: $("f-title").value.trim(),
      description: $("f-description").value.trim(),
      status: $("f-status").value,
      priority: $("f-priority").value,
      assignee_id: $("f-assignee").value || null,
      due_date: $("f-due").value || null,
    };
    if (!body.title) { errBox.textContent = "Title is required."; errBox.hidden = false; return; }
    const saveBtn = $("dialog-save");
    saveBtn.disabled = true;
    try {
      if (state.editingId) {
        await api("/api/tasks/" + state.editingId, { method: "PATCH", body: body });
        toast("Task updated.");
      } else {
        await api("/api/tasks", { method: "POST", body: body });
        toast("Task created.");
      }
      dialog.close();
      await refreshAll();
    } catch (err) {
      errBox.textContent = err.message; errBox.hidden = false;
    } finally { saveBtn.disabled = false; }
  });

  $("f-suggest").addEventListener("click", async function () {
    const text = ($("f-title").value + " " + $("f-description").value).trim();
    if (!text) { $("f-suggest-hint").textContent = "Add a title or description first."; return; }
    try {
      const r = await api("/api/ai/suggest-priority", { method: "POST", body: { text: text, due_date: $("f-due").value || null } });
      $("f-priority").value = r.priority;
      $("f-suggest-hint").textContent = "Rule-based suggestion: " + r.priority + ". Review before saving.";
    } catch (err) { $("f-suggest-hint").textContent = err.message; }
  });

  /* ---------- AI Assist ---------- */
  $("ai-example").addEventListener("click", function () {
    $("ai-text").value = "Production outage affecting all users; fix ASAP";
    $("ai-text").focus();
  });
  $("ai-form").addEventListener("submit", async function (e) {
    e.preventDefault();
    const out = $("ai-result");
    const text = $("ai-text").value.trim();
    if (!text) {
      out.hidden = false;
      out.innerHTML = '<p class="state error">Please describe the task first.</p>';
      return;
    }
    const btn = $("ai-btn");
    btn.disabled = true; btn.textContent = "Analysing...";
    try {
      const r = await api("/api/ai/suggest-priority", { method: "POST", body: { text: text, due_date: $("ai-due").value || null } });
      out.hidden = false;
      out.innerHTML = '<span class="badge b-' + esc(r.priority) + '">Suggested priority: ' + esc(r.priority) + "</span>" +
        "<p>" + esc(r.explanation) + "</p>" +
        (r.signals.length ? "<strong>Signals found</strong><ul>" + r.signals.map(function (s) { return "<li>" + esc(s) + "</li>"; }).join("") + "</ul>" : "") +
        '<div class="ai-tag">' + esc(r.disclaimer) + " Score: " + esc(r.score) + ".</div>" +
        (isStaff ? '<p><button class="btn btn-primary btn-sm" id="use-in-task" type="button">Create task with this priority</button></p>' : "");
      const use = $("use-in-task");
      if (use) {
        use.addEventListener("click", function () {
          showView("tasks");
          openDialog(null);
          $("f-description").value = text;
          $("f-priority").value = r.priority;
          $("f-due").value = $("ai-due").value;
        });
      }
    } catch (err) {
      out.hidden = false;
      out.innerHTML = '<p class="state error">' + esc(err.message) + "</p>";
    } finally { btn.disabled = false; btn.textContent = "Suggest priority"; }
  });

  /* ---------- user management (admin) ---------- */
  async function loadUsersTable() {
    const stateBox = $("users-state");
    const table = $("users-table");
    if (!stateBox) { return; }
    table.hidden = true;
    stateBox.className = "state";
    stateBox.innerHTML = '<span class="spinner"></span>Loading users...';
    try {
      await loadUsers();
      stateBox.textContent = "";
      $("users-body").innerHTML = state.users.map(function (u) {
        const self = u.id === me.id;
        return "<tr><td>" + esc(u.name) + (self ? " (you)" : "") + "</td><td>" + esc(u.email) + "</td><td>" +
          '<select class="role-select" data-id="' + u.id + '"' + (self ? " disabled" : "") + ">" +
          ["admin", "manager", "user"].map(function (r) { return "<option" + (r === u.role ? " selected" : "") + ">" + r + "</option>"; }).join("") +
          "</select></td><td>" +
          (self ? "" : '<button class="btn btn-ghost btn-sm btn-danger" data-user-delete="' + u.id + '" type="button">Delete</button>') +
          "</td></tr>";
      }).join("");
      table.hidden = false;
    } catch (err) {
      stateBox.className = "state error"; stateBox.textContent = err.message;
    }
  }
  if ($("users-body")) {
    $("users-body").addEventListener("change", async function (e) {
      if (!e.target.classList.contains("role-select")) { return; }
      try {
        await api("/api/users/" + e.target.dataset.id, { method: "PATCH", body: { role: e.target.value } });
        toast("Role updated.");
      } catch (err) { toast(err.message, "error"); }
      loadUsersTable();
    });
    $("users-body").addEventListener("click", async function (e) {
      const btn = e.target.closest("[data-user-delete]");
      if (!btn || !window.confirm("Delete this user? Their tasks will become unassigned.")) { return; }
      try {
        await api("/api/users/" + btn.dataset.userDelete, { method: "DELETE" });
        toast("User deleted.");
        await loadUsersTable();
        refreshAll();
      } catch (err) { toast(err.message, "error"); }
    });
  }

  /* ---------- start ---------- */
  showView("tasks");
  loadUsers().catch(function (err) { toast(err.message, "error"); });
  refreshAll();
})();
