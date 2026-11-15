/* The app pages (/ioContact/ and the others, made by tools/app-pages.py): copy buttons, the install tabs, the lightbox. */
(function () {
  "use strict";
  document.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-copy]");
    if (!btn) return;
    var text = "";
    btn.closest(".term").querySelector("pre code").childNodes.forEach(function (n) {
      if (n.nodeType === 1 && (n.classList.contains("p") || n.classList.contains("c"))) return;
      text += n.textContent;
    });
    var lines = text.split("\n").map(function (l) { return l.replace(/\s+$/, ""); }).filter(Boolean);
    navigator.clipboard.writeText(lines.join("\n")).then(function () {
      var old = btn.textContent;
      btn.textContent = "copied";
      setTimeout(function () { btn.textContent = old; }, 1400);
    });
  });

  var tabs = document.querySelectorAll(".tabs button");
  tabs.forEach(function (b) {
    b.addEventListener("click", function () {
      tabs.forEach(function (o) { o.setAttribute("aria-selected", o === b ? "true" : "false"); });
      document.querySelectorAll(".way").forEach(function (w) { w.hidden = w.dataset.way !== b.dataset.way; });
    });
  });

  var box = document.getElementById("lightbox");
  var boxImg = box.querySelector("img");
  var boxCap = document.getElementById("lb-cap");
  document.querySelectorAll("[data-full]").forEach(function (b) {
    b.addEventListener("click", function () {
      boxImg.src = b.dataset.full;
      boxImg.alt = b.dataset.cap;
      boxCap.textContent = b.dataset.cap;
      box.showModal();
    });
  });
  document.getElementById("lb-close").addEventListener("click", function () { box.close(); });
  box.addEventListener("click", function (e) { if (e.target === box) box.close(); });
})();
