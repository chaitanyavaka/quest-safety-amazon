initShell();

function initShell() {
  document.querySelectorAll("[data-logout]").forEach((button) => {
    button.addEventListener("click", async () => {
      await fetch("/api/auth/logout", { method: "POST" });
      window.location.href = "/login";
    });
  });

  refreshShellCounts();
  document.addEventListener("analysis:updated", refreshShellCounts);
}

async function refreshShellCounts() {
  try {
    const response = await fetch("/api/research/current");
    if (!response.ok) {
      return;
    }

    const data = await response.json();
    const rows = data.isReady ? data.results || [] : [];
    const reviewCount = rows.filter((item) => item.decision?.action === "HUMAN_REVIEW").length;

    document.querySelectorAll("#reviewNavCount").forEach((element) => {
      element.textContent = reviewCount;
    });
  } catch {
    document.querySelectorAll("#reviewNavCount").forEach((element) => {
      element.textContent = "0";
    });
  }
}
