/* Set the initial appearance/accent before the stylesheet paints.
   app.js will re-apply the authoritative settings from the backend. */
(() => {
  try {
    const raw = window.localStorage.getItem("autoscrcpy.settings.v1");
    const settings = raw ? JSON.parse(raw) : null;
    const accents = [
      "teal",
      "blue",
      "indigo",
      "violet",
      "rose",
      "amber",
      "lime",
      "slate",
    ];
    let appearance = "system";
    if (settings && typeof settings === "object") {
      if (accents.includes(settings.accent)) {
        document.documentElement.dataset.accent = settings.accent;
      }
      if (settings.appearance === "light" || settings.appearance === "dark") {
        appearance = settings.appearance;
      }
    }
    if (appearance === "system") {
      appearance = window.matchMedia?.("(prefers-color-scheme: light)")
        ?.matches
        ? "light"
        : "dark";
    }
    document.documentElement.dataset.appearance = appearance;
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) {
      meta.setAttribute(
        "content",
        appearance === "light" ? "#eef1f5" : "#080a0f"
      );
    }
  } catch {
    /* Keep the defaults from the HTML attributes. */
  }
})();
