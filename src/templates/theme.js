(function () {
  // Light/dark toggle. With nothing stored, the page follows the system
  // setting. Storage can be unavailable (private mode, file:// pages), so
  // every access is guarded and the page still works without it.
  var root = document.documentElement;
  var KEY = "hoodintel-theme";
  try {
    var saved = localStorage.getItem(KEY);
    if (saved === "light" || saved === "dark") root.setAttribute("data-theme", saved);
  } catch (e) {}

  function current() {
    var t = root.getAttribute("data-theme");
    if (t) return t;
    return window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }

  function label(btn) {
    var dark = current() === "dark";
    btn.textContent = dark ? "☀ Light mode" : "☾ Dark mode";
    btn.setAttribute("aria-pressed", String(dark));
  }

  document.addEventListener("DOMContentLoaded", function () {
    var btn = document.getElementById("theme-toggle");
    if (!btn) return;
    btn.hidden = false;
    label(btn);
    btn.addEventListener("click", function () {
      var next = current() === "dark" ? "light" : "dark";
      root.setAttribute("data-theme", next);
      try { localStorage.setItem(KEY, next); } catch (e) {}
      label(btn);
    });
  });
})();
