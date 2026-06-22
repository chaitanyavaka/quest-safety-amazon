const loginForm = document.querySelector("#loginForm");
const loginError = document.querySelector("#loginError");

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  loginError.hidden = true;

  const response = await fetch("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      username: document.querySelector("#loginUsername").value,
      password: document.querySelector("#loginPassword").value,
    }),
  });

  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    loginError.textContent = data.message || "Login failed.";
    loginError.hidden = false;
    return;
  }

  window.location.href = "/pipeline";
});
