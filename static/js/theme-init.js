// Runs before first paint: apply the saved theme (if any) so there is no flash. CSP-safe (external file).
(function () {
  try {
    var t = localStorage.getItem("ra-theme");
    if (t === "dark" || t === "light") document.documentElement.setAttribute("data-theme", t);
  } catch (e) { /* storage blocked: follow the OS */ }
})();
