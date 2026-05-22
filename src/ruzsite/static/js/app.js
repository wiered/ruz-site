
(() => {
  const THEME_KEY = "ruz-theme";
  const root = document.documentElement;

  function getTheme() {
    return root.dataset.theme === "light" ? "light" : "dark";
  }

  function applyTheme(theme) {
    root.dataset.theme = theme;

    for (const button of document.querySelectorAll("[data-theme-toggle]")) {
      const nextTheme = theme === "light" ? "dark" : "light";
      button.setAttribute("aria-pressed", String(theme === "light"));
      button.setAttribute("aria-label", `Switch to ${nextTheme} theme`);
      button.setAttribute("title", `Switch to ${nextTheme} theme`);
    }
  }

  function toggleTheme() {
    const nextTheme = getTheme() === "light" ? "dark" : "light";
    localStorage.setItem(THEME_KEY, nextTheme);
    applyTheme(nextTheme);
  }

  function initThemeControls() {
    applyTheme(getTheme());

    for (const button of document.querySelectorAll("[data-theme-toggle]")) {
      if (button.dataset.themeReady === "true") {
        continue;
      }

      button.dataset.themeReady = "true";
      button.addEventListener("click", toggleTheme);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initThemeControls, { once: true });
  } else {
    initThemeControls();
  }
})();
