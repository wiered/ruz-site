
(() => {
  const THEME_KEY = "ruz-theme";
  const STYLESHEET_KEY = "ruz-stylesheet";
  const STYLESHEET_VERSION = "2";
  const root = document.documentElement;

  function getSystemTheme() {
    return window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
  }

  function getStoredTheme() {
    const storedTheme = localStorage.getItem(THEME_KEY);
    return storedTheme === "light" || storedTheme === "dark" ? storedTheme : "system";
  }

  function getActiveTheme(themePreference = getStoredTheme()) {
    return themePreference === "system" ? getSystemTheme() : themePreference;
  }

  function applyTheme(themePreference = getStoredTheme()) {
    const activeTheme = getActiveTheme(themePreference);
    root.dataset.theme = activeTheme;
    root.dataset.themePreference = themePreference;

    for (const button of document.querySelectorAll("[data-theme-toggle]")) {
      const nextTheme = activeTheme === "light" ? "dark" : "light";
      button.setAttribute("aria-pressed", String(activeTheme === "light"));
      button.setAttribute("aria-label", `Switch to ${nextTheme} theme`);
      button.setAttribute("title", `Switch to ${nextTheme} theme`);
    }

    for (const button of document.querySelectorAll("[data-theme-choice]")) {
      const isActive = button.dataset.themeChoice === themePreference;
      button.dataset.active = String(isActive);
      button.setAttribute("aria-checked", String(isActive));
    }
  }

  function getStoredStylesheet() {
    return localStorage.getItem(STYLESHEET_KEY) === "compact" ? "compact" : "app";
  }

  function applyStylesheet(stylesheetName = getStoredStylesheet()) {
    const normalizedStylesheet = stylesheetName === "compact" ? "compact" : "app";
    const stylesheet = document.getElementById("app-stylesheet");
    if (stylesheet instanceof HTMLLinkElement) {
      stylesheet.href = `/static/css/${normalizedStylesheet}.css?v=${STYLESHEET_VERSION}`;
    }

    root.dataset.stylesheet = normalizedStylesheet;

    for (const button of document.querySelectorAll("[data-stylesheet-choice]")) {
      const isActive = button.dataset.stylesheetChoice === normalizedStylesheet;
      button.dataset.active = String(isActive);
      button.setAttribute("aria-checked", String(isActive));
    }
  }

  function toggleTheme() {
    const nextTheme = getActiveTheme() === "light" ? "dark" : "light";
    localStorage.setItem(THEME_KEY, nextTheme);
    applyTheme(nextTheme);
  }

  function selectTheme(event) {
    const button = event.currentTarget;
    const themePreference = button.dataset.themeChoice;
    if (!themePreference) {
      return;
    }

    if (themePreference === "system") {
      localStorage.removeItem(THEME_KEY);
      applyTheme("system");
      return;
    }

    localStorage.setItem(THEME_KEY, themePreference);
    applyTheme(themePreference);
  }

  function selectStylesheet(event) {
    const button = event.currentTarget;
    const stylesheetName = button.dataset.stylesheetChoice;
    if (!stylesheetName) {
      return;
    }

    const normalizedStylesheet = stylesheetName === "compact" ? "compact" : "app";
    localStorage.setItem(STYLESHEET_KEY, normalizedStylesheet);
    applyStylesheet(normalizedStylesheet);
  }

  function initThemeControls() {
    applyTheme();
    applyStylesheet();

    for (const button of document.querySelectorAll("[data-theme-toggle]")) {
      if (button.dataset.themeReady === "true") {
        continue;
      }

      button.dataset.themeReady = "true";
      button.addEventListener("click", toggleTheme);
    }

    for (const button of document.querySelectorAll("[data-theme-choice]")) {
      if (button.dataset.themeReady === "true") {
        continue;
      }

      button.dataset.themeReady = "true";
      button.addEventListener("click", selectTheme);
    }

    for (const button of document.querySelectorAll("[data-stylesheet-choice]")) {
      if (button.dataset.stylesheetReady === "true") {
        continue;
      }

      button.dataset.stylesheetReady = "true";
      button.addEventListener("click", selectStylesheet);
    }

    const mediaQuery = window.matchMedia("(prefers-color-scheme: light)");
    if (root.dataset.themeListenerReady !== "true") {
      root.dataset.themeListenerReady = "true";
      mediaQuery.addEventListener("change", () => {
        if (getStoredTheme() === "system") {
          applyTheme("system");
        }
      });
    }
  }

  function lockSubgroupForm(form) {
    const buttons = form.querySelectorAll(".theme-choice");
    for (const button of buttons) {
      button.disabled = true;
    }

    window.setTimeout(() => {
      for (const button of buttons) {
        button.disabled = false;
      }
    }, 1000);
  }

  function initSubgroupControls() {
    for (const form of document.querySelectorAll(".settings-subgroup-form")) {
      if (form.dataset.subgroupReady === "true") {
        continue;
      }

      form.dataset.subgroupReady = "true";
      form.addEventListener("submit", () => {
        // Wait until the browser serializes the successful submit button.
        window.setTimeout(() => {
          lockSubgroupForm(form);
        }, 0);
      });
    }
  }

  function clearSettingsBanners(pageContent) {
    for (const banner of pageContent.querySelectorAll(".settings-banner")) {
      banner.remove();
    }
  }

  function showSettingsBanner(message, variant = "error") {
    const pageContent = document.querySelector(".page-content");
    if (!pageContent) {
      return;
    }

    clearSettingsBanners(pageContent);

    const banner = document.createElement("div");
    banner.className = `card settings-banner settings-banner-${variant}`;
    banner.textContent = message;
    pageContent.prepend(banner);
  }

  function replaceSettingsContent(html) {
    const pageContent = document.querySelector(".page-content");
    if (!pageContent) {
      return;
    }

    const parser = new DOMParser();
    const nextDocument = parser.parseFromString(html, "text/html");
    const nextPageContent = nextDocument.querySelector(".page-content");
    if (!nextPageContent) {
      return;
    }

    pageContent.innerHTML = nextPageContent.innerHTML;
    initThemeControls();
    initSubgroupControls();
    initSettingsFormEnhancements();
  }

  async function submitSettingsForm(form) {
    const submitter = form.dataset.pendingSubmitterName
      ? {
          name: form.dataset.pendingSubmitterName,
          value: form.dataset.pendingSubmitterValue ?? "",
        }
      : null;
    delete form.dataset.pendingSubmitterName;
    delete form.dataset.pendingSubmitterValue;

    const formData = new FormData(form);
    if (submitter && !formData.has(submitter.name)) {
      formData.append(submitter.name, submitter.value);
    }

    const response = await fetch(form.action, {
      method: form.method || "POST",
      body: formData,
      credentials: "same-origin",
      headers: {
        Accept: "text/html, application/json",
      },
    });

    const contentType = response.headers.get("content-type") ?? "";
    if (contentType.includes("text/html")) {
      replaceSettingsContent(await response.text());
      return;
    }

    if (contentType.includes("application/json")) {
      const payload = await response.json();
      const detail = payload?.detail;
      if (typeof detail === "string" && detail.length > 0) {
        showSettingsBanner(detail, "error");
        return;
      }
    }

    showSettingsBanner("Could not update settings right now.", "error");
  }

  function initSettingsFormEnhancements() {
    for (const form of document.querySelectorAll(".settings-subgroup-form, .settings-result-card")) {
      if (form.dataset.settingsAsyncReady === "true") {
        continue;
      }

      form.dataset.settingsAsyncReady = "true";
      form.addEventListener("click", (event) => {
        const submitter = event.target.closest('button[type="submit"], input[type="submit"]');
        if (!(submitter instanceof HTMLElement) || !form.contains(submitter)) {
          return;
        }

        const { name } = submitter;
        if (!name) {
          return;
        }

        form.dataset.pendingSubmitterName = name;
        form.dataset.pendingSubmitterValue = submitter.value;
      });

      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        try {
          await submitSettingsForm(form);
        } catch {
          showSettingsBanner("Could not update settings right now.", "error");
        }
      });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => {
      initThemeControls();
      initSubgroupControls();
      initSettingsFormEnhancements();
    }, { once: true });
  } else {
    initThemeControls();
    initSubgroupControls();
    initSettingsFormEnhancements();
  }
})();
