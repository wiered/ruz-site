const statusNode = document.getElementById("telegram-auth-status");
const isAuthenticated = document.body?.dataset.authenticated === "true";

function setStatus(message, isError = false) {
  if (!statusNode) {
    return;
  }

  statusNode.textContent = message;
  statusNode.className = isError ? "error" : "muted";
}

async function bootstrapTelegramAuth() {
  if (isAuthenticated) {
    return;
  }

  const webApp = window.Telegram?.WebApp;
  const initData = webApp?.initData;
  if (!initData) {
    setStatus("Telegram Mini App initData is not available in this browser session.");
    return;
  }

  webApp.ready();
  setStatus("Signing in with Telegram...");

  try {
    const response = await fetch("/auth/telegram", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({ initData }),
    });

    if (!response.ok) {
      const payload = await response.json().catch(() => null);
      const detail = payload?.detail ?? "Telegram authorization failed.";
      throw new Error(detail);
    }

    window.location.reload();
  } catch (error) {
    const message = error instanceof Error ? error.message : "Telegram authorization failed.";
    setStatus(message, true);
  }
}

void bootstrapTelegramAuth();
