const registerForm = document.getElementById("registerForm");
const loginForm    = document.getElementById("loginForm");
const message      = document.getElementById("message");

// ── Register ─────────────────────────────────────────────────────────────────
if (registerForm) {
  registerForm.addEventListener("submit", async function(event) {
    event.preventDefault();

    const username = document.getElementById("username").value.trim();
    const email    = document.getElementById("email")?.value.trim() || `${username}@exam.com`;
    const password = document.getElementById("password").value;

    if (!username || !password) {
      message.style.color = "red";
      message.textContent = "Please fill all fields.";
      return;
    }

    try {
      const response = await fetch(`${API_BASE_URL}/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, email, password })
      });

      const data = await response.json();

      if (!response.ok) {
        message.style.color = "red";
        message.textContent = data.detail || "Registration failed";
        return;
      }

      message.style.color = "green";
      message.textContent = "✅ Account created! Redirecting to login...";
      setTimeout(() => { window.location.href = "login.html"; }, 1200);

    } catch (err) {
      message.style.color = "red";
      message.textContent = "Server error. Is the backend running?";
      console.error(err);
    }
  });
}

// ── Login ─────────────────────────────────────────────────────────────────────
if (loginForm) {
  loginForm.addEventListener("submit", async function(event) {
    event.preventDefault();

    const usernameField = document.getElementById("loginEmail") || document.getElementById("loginUsername");
    const passwordField = document.getElementById("loginPassword");

    if (!usernameField || !passwordField) return;

    const formData = new FormData();
    formData.append("username", usernameField.value.trim());
    formData.append("password", passwordField.value);

    try {
      const response = await fetch(`${API_BASE_URL}/auth/login`, {
        method: "POST",
        body: formData
      });

      const data = await response.json();

      if (!response.ok) {
        message.style.color = "red";
        message.textContent = data.detail || "Login failed";
        return;
      }

      localStorage.setItem("token", data.access_token);
      window.location.href = "exams.html";

    } catch (err) {
      message.style.color = "red";
      message.textContent = "Server error. Is the backend running?";
      console.error(err);
    }
  });
}