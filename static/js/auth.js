/* Login and registration pages. */
(function () {
  "use strict";
  const form = document.getElementById("login-form") || document.getElementById("register-form");
  if (!form) { return; }
  const isRegister = form.id === "register-form";
  const errorBox = document.getElementById("form-error");
  const button = document.getElementById("submit-btn");
  const idleLabel = button.textContent;

  function showError(message) {
    errorBox.textContent = message;
    errorBox.hidden = false;
  }

  document.querySelectorAll(".chip[data-email]").forEach(function (chip) {
    chip.addEventListener("click", function () {
      document.getElementById("email").value = chip.dataset.email;
      document.getElementById("password").value = chip.dataset.password;
      errorBox.hidden = true;
    });
  });

  form.addEventListener("submit", async function (event) {
    event.preventDefault();
    errorBox.hidden = true;

    const email = document.getElementById("email").value.trim();
    const password = document.getElementById("password").value;
    const body = { email: email, password: password };

    if (isRegister) {
      body.name = document.getElementById("name").value.trim();
      if (password !== document.getElementById("confirm").value) {
        showError("Passwords do not match.");
        return;
      }
    }
    if (!email || !password) {
      showError("Please enter your email and password.");
      return;
    }

    button.disabled = true;
    button.textContent = isRegister ? "Creating account..." : "Logging in...";
    try {
      await TF.api(isRegister ? "/api/auth/register" : "/api/auth/login", {
        method: "POST", body: body, noRedirect: true,
      });
      window.location.href = "/";
    } catch (err) {
      showError(err.message);
      button.disabled = false;
      button.textContent = idleLabel;
    }
  });
})();
