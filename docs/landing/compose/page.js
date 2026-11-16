/* The page around compose.js: the form, the file as it is typed, what is still missing, download, copy, and reading
   a file made here back in. Nothing is sent anywhere and nothing is stored: the answers live in `state` until the
   page is closed (they are also in the file, which is how they come back). */
(function () {
  "use strict";
  var C = window.ioCompose;
  var $ = function (id) { return document.getElementById(id); };
  var form = $("form");

  function password() {
    var abc = "abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789", out = "", n = new Uint32Array(24);
    crypto.getRandomValues(n);
    for (var i = 0; i < n.length; i++) out += abc[n[i] % abc.length];
    return out;
  }
  function zone() {
    try { return Intl.DateTimeFormat().resolvedOptions().timeZone || ""; } catch (e) { return ""; }
  }
  var state = C.defaults(password, zone());
  var touched = {};      // the fields somebody has been in: only those are marked wrong while typing
  var asked = false;     // download or copy was tried: every wrong field is marked

  function esc(s) { return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;"); }
  function get(path) { return path.split(".").reduce(function (o, k) { return o == null ? o : o[k]; }, view()); }
  function set(path, v) {
    var keys = path.split("."), o = state;
    for (var i = 0; i < keys.length - 1; i++) o = o[keys[i]];
    o[keys[keys.length - 1]] = v;
  }
  function view() { return Object.assign({}, state, {layout: C.layout(state)}); }

  /* data-if="a.b=x|y&!c.d&e": every part must hold */
  function holds(expr) {
    return expr.split("&").every(function (part) {
      var not = part.charAt(0) === "!", p = not ? part.slice(1) : part, eq = p.indexOf("=");
      if (eq < 0) {
        var any = p.split("|").some(function (k) { return !!get(k); });
        return not ? !any : any;
      }
      var v = String(get(p.slice(0, eq))), ok = p.slice(eq + 1).split("|").indexOf(v) >= 0;
      return not ? !ok : ok;
    });
  }

  /* ---- the parts of the form that are drawn from the list of apps ---- */
  function drawApps() {
    function tile(a) {
      return '<label><input type="checkbox" data-app="' + a.key + '"><img src="/img/' + a.key + '.svg" alt="" width="38" height="38"><b>' + a.name + "</b><small>" + esc(a.what) + "</small></label>";
    }
    $("apps").innerHTML = C.APPS.filter(function (a) { return !a.tool; }).map(tile).join("");
    $("tools").innerHTML = C.APPS.filter(function (a) { return a.tool; }).map(tile).join("");
  }
  function drawNames() {
    var dom = state.reach.domain.trim().toLowerCase() || "example.com";
    var want = C.APPS.filter(function (a) { return state.apps[a.key]; }).map(function (a) { return a.key; }).join(",");
    var box = $("names");
    if (box.dataset.for !== want) {   // only when the apps changed: typing in a name must not redraw its box
      box.dataset.for = want;
      box.innerHTML = C.APPS.filter(function (a) { return state.apps[a.key]; }).map(function (a) {
        return '<label class="name"><span>' + a.name + '</span><input type="text" data-k="reach.names.' + a.key + '" spellcheck="false" autocapitalize="off" aria-label="' + a.name + ' name"><i></i></label>';
      }).join("");
    }
    box.querySelectorAll("i").forEach(function (i) { i.textContent = "." + dom; });
  }
  function drawZones() {
    try {
      $("zones").innerHTML = Intl.supportedValuesOf("timeZone").map(function (z) { return '<option value="' + esc(z) + '">'; }).join("");
    } catch (e) { /* an older browser: the field is still a text box */ }
  }

  /* ---- state -> form ---- */
  function fill() {
    form.querySelectorAll("[data-app]").forEach(function (el) { el.checked = !!state.apps[el.dataset.app]; });
    form.querySelectorAll("input[type=radio]").forEach(function (el) { el.checked = String(get(el.name)) === el.value; });
    form.querySelectorAll("[data-k]").forEach(function (el) {
      if (el === document.activeElement) return;
      var v = get(el.dataset.k);
      if (el.type === "checkbox") el.checked = !!v; else el.value = v == null ? "" : v;
    });
  }

  /* ---- the file ---- */
  function secrets() {
    var d = state.db, out = [state.admin.password];
    if (d.mode === "existing") out.push(d.password, d.sharedPassword, d.adminPassword);
    else out.push(d.rootPassword, d.password, d.sharedPassword);
    return out.filter(Boolean);
  }
  function shown(yaml) {
    if ($("reveal").checked) return esc(yaml);
    var text = yaml;
    secrets().forEach(function (s) { text = text.split(C.quoted(s)).join('"\u0000"'); });
    text = text.replace(/^(# answers: ).*$/m, "$1\u0000");
    return esc(text).replace(/\u0000/g, '<span class="dots">••••••••</span>');
  }

  var built = null;
  function render() {
    drawNames();
    fill();
    document.querySelectorAll("[data-if]").forEach(function (el) { el.hidden = !holds(el.dataset.if); });
    built = C.build(state, new Date().toISOString().slice(0, 10));
    $("yaml").innerHTML = shown(built.yaml).split("\n").map(function (l) {
      return /^\s*#/.test(l) ? '<span class="c">' + l + "</span>" : l.replace(/(\s+#\s.*)$/, '<span class="c">$1</span>');
    }).join("\n");

    var wrong = {};
    built.problems.forEach(function (p) { wrong[p.at] = p.text; });
    form.querySelectorAll("[data-k], input[type=radio]").forEach(function (el) {
      var k = el.dataset.k || el.name;
      if (wrong[k] && (asked || touched[k])) el.setAttribute("aria-invalid", "true"); else el.removeAttribute("aria-invalid");
    });
    var st = $("status"), n = built.problems.length;
    if (n) {
      st.className = "cstatus need";
      st.innerHTML = "<b>" + (n === 1 ? "One answer" : n + " answers") + " still needed</b><ul>" + built.problems.map(function (p) {
        return '<li><button type="button" class="linkish" data-go="' + esc(p.at) + '">' + esc(p.text) + "</button></li>";
      }).join("") + "</ul>";
    } else {
      st.className = "cstatus ready";
      st.innerHTML = "<b>Ready.</b> " + C.APPS.filter(function (a) { return state.apps[a.key]; }).length + " app" +
        (C.APPS.filter(function (a) { return state.apps[a.key]; }).length === 1 ? "" : "s") +
        (state.db.mode === "existing" ? " on your database server" : " and MariaDB") + (state.reach.https === "caddy" ? ", with HTTPS" : "") + ".";
    }
    $("download").disabled = $("copy").disabled = !!n;
    $("download").title = $("copy").title = n ? "Answer what is still needed first" : "";

    $("steps").innerHTML = built.steps.map(function (s, i) {
      var code = s.code ? '<div class="term"><div class="term-head"><span>' + esc(s.head || "") + '</span><button class="copy" type="button" data-copy>copy</button></div><pre><code>' +
        esc(n && s.title === "Create the databases" ? s.code.replace(/IDENTIFIED BY '.*'/g, "IDENTIFIED BY '…'") : s.code).split("\n").map(function (l) {
          return l.replace(/(\s+#\s.*)$/, '<span class="c">$1</span>');
        }).join("\n") + "</code></pre></div>" : "";
      return '<li><h3><span class="chip">' + (i + 1) + "</span> " + esc(s.title) + "</h3><p>" + esc(s.text) + "</p>" + code + "</li>";
    }).join("");
  }

  /* ---- form -> state ---- */
  function take(el) {
    if (el.dataset.app) { state.apps[el.dataset.app] = el.checked; touched.apps = true; }
    else if (el.type === "radio") { if (el.checked) set(el.name, el.value); touched[el.name] = true; }
    else if (el.dataset.k) { set(el.dataset.k, el.type === "checkbox" ? el.checked : el.value); }
    else return;
    render();
  }
  form.addEventListener("input", function (e) { take(e.target); });
  form.addEventListener("change", function (e) { take(e.target); });
  form.addEventListener("focusout", function (e) {
    if (e.target.dataset && e.target.dataset.k) { touched[e.target.dataset.k] = true; render(); }
  });
  form.addEventListener("submit", function (e) { e.preventDefault(); });

  /* the admin's password: show it, or make one (shown, so it can be noted) */
  function reveal(on) {
    $("admin-password").type = on ? "text" : "password";
    $("admin-show").setAttribute("aria-pressed", on ? "true" : "false");
    $("admin-show").textContent = on ? "Hide" : "Show";
  }
  $("admin-show").addEventListener("click", function () { reveal($("admin-password").type === "password"); });
  $("admin-make").addEventListener("click", function () {
    state.admin.password = password().slice(0, 16);
    reveal(true);
    render();
  });
  $("reveal").addEventListener("change", render);

  /* a problem in the list leads to its field */
  $("status").addEventListener("click", function (e) {
    var b = e.target.closest("[data-go]");
    if (!b) return;
    var k = b.dataset.go;
    var el = k === "apps" ? form.querySelector("[data-app]") :
      Array.prototype.filter.call(form.querySelectorAll('[data-k="' + k + '"], input[name="' + k + '"]'), function (x) { return x.offsetParent !== null; })[0];
    if (el) { touched[k] = true; el.focus(); el.scrollIntoView({block: "center", behavior: "smooth"}); render(); }
  });

  /* ---- the file out ---- */
  function ready() {
    if (built && !built.problems.length) return true;
    asked = true;
    render();
    $("status").scrollIntoView({block: "nearest", behavior: "smooth"});
    return false;
  }
  function said(btn, text) {
    var old = btn.dataset.label || (btn.dataset.label = btn.innerHTML);
    btn.textContent = text;
    setTimeout(function () { btn.innerHTML = old; }, 1600);
  }
  $("download").addEventListener("click", function () {
    if (!ready()) return;
    var a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([built.yaml], {type: "text/yaml"}));
    a.download = "docker-compose.yml";
    document.body.appendChild(a);
    a.click();
    setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 500);
  });
  $("copy").addEventListener("click", function () {
    if (!ready()) return;
    navigator.clipboard.writeText(built.yaml).then(function () { said($("copy"), "copied"); });
  });
  document.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-copy]");
    if (!btn) return;
    var text = "";
    btn.closest(".term").querySelector("pre code").childNodes.forEach(function (n) {
      if (n.nodeType === 1 && n.classList.contains("c")) return;   // the comments stay on the page
      text += n.textContent;
    });
    navigator.clipboard.writeText(text.split("\n").map(function (l) { return l.replace(/\s+$/, ""); }).join("\n")).then(function () { said(btn, "copied"); });
  });

  /* ---- a file made here, read back ---- */
  function open(text) {
    var got = C.answersIn(text, password, zone());
    var note = document.createElement("span");
    note.className = "opened";
    note.setAttribute("role", "status");
    if (got) {
      state = got;
      touched = {};
      asked = false;
      $("names").dataset.for = "";
      render();
      note.textContent = "Opened: the form holds that file's answers.";
    } else {
      note.textContent = "That file was not made on this page (it has no answers line), so there is nothing to read back.";
      note.className = "opened no";
    }
    document.querySelectorAll(".opened").forEach(function (o) { o.remove(); });
    $("open-btn").after(note);
  }
  $("open-btn").addEventListener("click", function () { $("open-file").click(); });
  $("open-file").addEventListener("change", function () {
    var f = this.files[0];
    if (!f) return;
    var r = new FileReader();
    r.onload = function () { open(String(r.result)); };
    r.readAsText(f);
    this.value = "";
  });
  document.addEventListener("dragover", function (e) { e.preventDefault(); });
  document.addEventListener("drop", function (e) {
    e.preventDefault();
    var f = e.dataTransfer && e.dataTransfer.files[0];
    if (f) f.text().then(open);
  });

  drawApps();
  drawZones();
  render();
})();
