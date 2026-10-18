// Explore page: filter claims and term pairs from JSON embedded in the page. Text is inserted with textContent.
(function () {
  var claims = JSON.parse(document.getElementById("data-claims").textContent);
  var terms = JSON.parse(document.getElementById("data-terms").textContent);

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text != null) node.textContent = text;
    return node;
  }
  function citeB(r) {
    var a = el("a", "cite", r.b || "[B:?]");
    if (r.row != null) a.href = "pages/" + r.row + ".html";
    return a;
  }
  function citeW(r) {
    var a = el("a", "cite", r.w || "[W:?]");
    if (r.rev) { a.href = r.rev; a.target = "_blank"; a.rel = "noopener"; }
    return a;
  }
  function quoteCell(cite, quote, label, missing) {
    var td = el("td", "qcell");
    td.appendChild(cite);
    if (label) td.appendChild(el("span", "small muted", " " + label));
    td.appendChild(el("div", "qt", quote ? "“" + quote + "”" : "(no quote)"));
    return td;
  }
  function hay(r, keys) {
    return keys.map(function (k) { return r[k] || ""; }).join(" ").toLowerCase();
  }
  claims.forEach(function (r) { r._s = hay(r, ["claim", "qb", "qw", "head", "title", "b", "w", "tag"]); });
  terms.forEach(function (r) { r._s = hay(r, ["old", "new", "qb", "qw", "head", "title", "b", "w"]); });

  var qc = document.getElementById("q-claims"), tbodyC = document.getElementById("rows-claims");
  function renderClaims() {
    var q = qc.value.toLowerCase().trim(), on = {};
    document.querySelectorAll(".tagbox").forEach(function (c) { on[c.value] = c.checked; });
    var frag = document.createDocumentFragment(), n = 0;
    claims.forEach(function (r) {
      if (!on[r.tag] || (q && r._s.indexOf(q) < 0)) return;
      n++;
      var tr = el("tr");
      var td = el("td"); td.appendChild(el("span", "tag " + r.tag, r.tag)); tr.appendChild(td);
      tr.appendChild(el("td", "claimtext", r.claim || ""));
      tr.appendChild(quoteCell(citeB(r), r.qb, r.head));
      tr.appendChild(quoteCell(citeW(r), r.qw, r.title, r.tag === "dropped" ? "(not found in the article)" : null));
      frag.appendChild(tr);
    });
    tbodyC.replaceChildren(frag);
    document.getElementById("n-claims").textContent = n + " of " + claims.length + " claims";
  }

  var qt = document.getElementById("q-terms"), tbodyT = document.getElementById("rows-terms");
  var showOcr = document.getElementById("show-ocr");
  function renderTerms() {
    var q = qt.value.toLowerCase().trim(), frag = document.createDocumentFragment(), n = 0;
    terms.forEach(function (r) {
      if ((r.ocr && !showOcr.checked) || (q && r._s.indexOf(q) < 0)) return;
      n++;
      var tr = el("tr", r.ocr ? "ocr" : "");
      var old = el("td", "old", r.old || "");
      if (r.ocr) old.appendChild(el("span", "badge", "likely OCR or spelling"));
      tr.appendChild(old);
      tr.appendChild(el("td", "new", r.new || ""));
      tr.appendChild(quoteCell(citeB(r), r.qb, r.head));
      tr.appendChild(quoteCell(citeW(r), r.qw, r.title));
      frag.appendChild(tr);
    });
    tbodyT.replaceChildren(frag);
    document.getElementById("n-terms").textContent = n + " of " + terms.length + " term pairs";
  }

  qc.addEventListener("input", renderClaims);
  document.querySelectorAll(".tagbox").forEach(function (c) { c.addEventListener("change", renderClaims); });
  qt.addEventListener("input", renderTerms);
  showOcr.addEventListener("change", renderTerms);

  document.querySelectorAll(".tab").forEach(function (b) {
    b.addEventListener("click", function () {
      document.querySelectorAll(".tab").forEach(function (x) { x.classList.toggle("active", x === b); });
      document.getElementById("tab-claims").hidden = b.dataset.tab !== "claims";
      document.getElementById("tab-terms").hidden = b.dataset.tab !== "terms";
    });
  });
  if (location.hash === "#terms") document.querySelector('.tab[data-tab="terms"]').click();
  renderClaims();
  renderTerms();
})();
