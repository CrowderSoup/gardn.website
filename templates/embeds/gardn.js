(function () {
  function escapeHtml(value) {
    return String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function stripScheme(url) {
    return String(url || "").replace(/^https?:\/\//, "").replace(/\/$/, "");
  }

  function ensureWidgetStyles() {
    if (document.getElementById("gardn-widget-style")) return;
    var style = document.createElement("style");
    style.id = "gardn-widget-style";
    style.textContent =
      /* single plant widget */
      ".gardn-widget{max-width:380px;font-family:'Avenir Next','Trebuchet MS','Gill Sans',sans-serif;color:#1e2f2a}" +
      ".gardn-widget .card{display:block;background:#fff;border:1px solid #c8d3b6;border-radius:16px;padding:.75rem;box-shadow:0 10px 30px rgba(35,69,43,.12)}" +
      ".gardn-widget p{margin:.2rem 0}" +
      ".gardn-widget .plant-link{display:inline-block}" +
      ".gardn-widget .plant-img{display:block;max-width:100%;height:auto}" +
      ".gardn-widget .pick-box{border-top:1px dashed #cad7bc;margin-top:.6rem;padding-top:.6rem}" +
      ".gardn-widget .pick-count{margin:0 0 .5rem}" +
      ".gardn-widget .btn{display:inline-flex;align-items:center;justify-content:center;background:linear-gradient(180deg,#2f7a4a,#185a35);color:#fff;border:0;border-radius:10px;padding:.52rem .82rem;text-decoration:none;font-weight:600}" +
      /* roll widget */
      ".gardn-roll{display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:.75rem;font-family:'Avenir Next','Trebuchet MS','Gill Sans',sans-serif}" +
      ".gardn-roll-card{display:flex;flex-direction:column;background:#fff;border:1px solid #c8d3b6;border-radius:16px;padding:.75rem;box-shadow:0 10px 30px rgba(35,69,43,.12);text-decoration:none;color:#1e2f2a;transition:transform 180ms ease,box-shadow 180ms ease}" +
      ".gardn-roll-card:hover{transform:translateY(-2px);box-shadow:0 14px 32px rgba(35,69,43,.16)}" +
      ".gardn-roll-plant{display:block;width:100%;height:auto;border-radius:8px;border:1px solid #dae3cd;background:linear-gradient(180deg,#f8fbf2,#eff6e5);margin-bottom:.4rem}" +
      ".gardn-roll-name{display:block;font-size:.9rem;font-weight:600;margin-bottom:.15rem}" +
      ".gardn-roll-domain{display:block;font-size:.75rem;color:#476056;overflow-wrap:anywhere}";
    document.head.appendChild(style);
  }

  /* ── single plant widget ── */

  function renderFallback(el, username) {
    var profileUrl = "{{ public_base }}/u/" + encodeURIComponent(username) + "/";
    var a = document.createElement("a");
    a.href = profileUrl;
    a.target = "_top";
    a.rel = "noopener noreferrer";
    a.textContent = "View this garden on Gardn";
    el.innerHTML = "";
    el.appendChild(a);
  }

  function renderPlant(el, data) {
    var name = escapeHtml(data.display_name || data.username);
    var domain = escapeHtml(data.identity_domain || data.username);
    var wrapper = document.createElement("div");
    wrapper.className = "gardn-widget";
    wrapper.innerHTML =
      '<article class="card compact">' +
      '<p><a href="' + data.me_url + '" target="_top" rel="noopener noreferrer">' + name + "</a></p>" +
      '<p><a class="plant-link" href="' + data.me_url + '" target="_top" rel="noopener noreferrer">' +
      '<img class="plant-img" src="' + data.plant_svg_url + '" alt="Plant for ' + domain + '" loading="lazy" width="180" height="140" />' +
      "</a></p>" +
      '<div class="pick-box"><p class="pick-count">Picks: ' + data.pick_count + '</p>' +
      (data.has_picked
        ? '<span class="btn">You picked this</span>'
        : '<a class="btn" href="' + data.login_to_pick_url + '" target="_top" rel="noopener noreferrer">Login to pick</a>') +
      "</div>" +
      "</article>";
    el.innerHTML = "";
    el.appendChild(wrapper);
  }

  /* ── roll widget ── */

  function renderRollFallback(el, username) {
    var profileUrl = "{{ public_base }}/u/" + encodeURIComponent(username) + "/";
    var a = document.createElement("a");
    a.href = profileUrl;
    a.target = "_top";
    a.rel = "noopener noreferrer";
    a.textContent = "View this garden on Gardn";
    el.innerHTML = "";
    el.appendChild(a);
  }

  function renderRoll(el, data) {
    if (!data.roll || !data.roll.length) {
      el.textContent = "No picks yet.";
      return;
    }
    var html = '<div class="gardn-roll">';
    data.roll.forEach(function (row) {
      var name = escapeHtml(row.display_name || row.username);
      var domain = escapeHtml(stripScheme(row.me_url));
      html +=
        '<a class="gardn-roll-card" href="' + row.me_url + '" target="_top" rel="noopener noreferrer">' +
        '<img class="gardn-roll-plant" src="' + row.plant_svg_url + '" alt="Plant for ' + domain + '" loading="lazy" width="120" height="96" />' +
        '<strong class="gardn-roll-name">' + name + "</strong>" +
        '<small class="gardn-roll-domain">' + domain + "</small>" +
        "</a>";
    });
    html += "</div>";
    el.innerHTML = html;
  }

  /* ── init ── */

  ensureWidgetStyles();

  document.querySelectorAll("[data-gardn]").forEach(function (node) {
    var username = node.getAttribute("data-gardn");
    fetch("{{ public_base }}/api/" + encodeURIComponent(username) + "/plant.json")
      .then(function (r) {
        if (!r.ok) throw new Error("fetch failed");
        return r.json();
      })
      .then(function (data) { renderPlant(node, data); })
      .catch(function () { renderFallback(node, username); });
  });

  document.querySelectorAll("[data-gardn-roll]").forEach(function (node) {
    var username = node.getAttribute("data-gardn-roll");
    fetch("{{ public_base }}/api/" + encodeURIComponent(username) + "/roll.json")
      .then(function (r) {
        if (!r.ok) throw new Error("fetch failed");
        return r.json();
      })
      .then(function (data) { renderRoll(node, data); })
      .catch(function () { renderRollFallback(node, username); });
  });
})();
