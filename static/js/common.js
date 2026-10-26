/* Shared helpers: API client (session cookies + safe JSON handling), toasts, escaping. */
(function () {
  "use strict";

  class ApiError extends Error {
    constructor(message, status, details) {
      super(message);
      this.status = status || 0;
      this.details = details || null;
    }
  }

  /**
   * Call the Flask JSON API.
   * - always sends the session cookie (credentials: "same-origin")
   * - sends JSON bodies with the correct Content-Type
   * - never calls res.json() blindly: a non-JSON answer becomes a clear error, not a crash
   * - a 401 on a protected page sends the user to the login screen
   */
  async function api(path, options) {
    options = options || {};
    const init = {
      method: options.method || "GET",
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    };
    if (options.body !== undefined) {
      init.headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(options.body);
    }

    let res;
    try {
      res = await fetch(path, init);
    } catch (networkError) {
      throw new ApiError("Cannot reach the server. Check that TaskFlow is running and try again.", 0);
    }

    let data = null;
    const type = res.headers.get("content-type") || "";
    if (type.indexOf("application/json") !== -1) {
      try { data = await res.json(); } catch (parseError) { data = null; }
    }

    if (res.status === 401 && !options.noRedirect) {
      window.location.href = "/login";
      throw new ApiError((data && data.error) || "Please log in.", 401);
    }
    if (!res.ok) {
      throw new ApiError((data && data.error) || "Request failed (" + res.status + ").", res.status, data && data.details);
    }
    if (data === null) {
      throw new ApiError("The server sent an unexpected response. Please refresh the page.", res.status);
    }
    return data;
  }

  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function toast(message, type) {
    const box = document.getElementById("toasts");
    if (!box) { return; }
    const el = document.createElement("div");
    el.className = "toast " + (type || "success");
    el.textContent = message;
    box.appendChild(el);
    setTimeout(function () { el.remove(); }, 4000);
  }

  window.TF = { api: api, ApiError: ApiError, esc: esc, toast: toast };
})();
