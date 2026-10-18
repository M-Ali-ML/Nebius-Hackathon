// Small helpers: filter the page list, toggle bbox classes, link entries to their blocks.
(function () {
  function pressed(b) { return b.getAttribute("aria-pressed") === "true"; }

  // Index: text search plus one filter chip at a time.
  var filter = document.getElementById("filter");
  if (filter) {
    var chips = document.querySelectorAll("#index-filters .chip");
    var shown = document.getElementById("n-shown");
    var current = "all";
    function applyFilter() {
      var q = filter.value.toLowerCase().trim(), n = 0;
      document.querySelectorAll("#pages tbody tr").forEach(function (tr) {
        var tags = " " + tr.dataset.tags + " ";
        var ok = tr.dataset.search.indexOf(q) >= 0 && (current === "all" || tags.indexOf(" " + current + " ") >= 0);
        tr.hidden = !ok;
        if (ok) n++;
      });
      if (shown) shown.textContent = n + " of " + document.querySelectorAll("#pages tbody tr").length;
    }
    chips.forEach(function (c) {
      c.addEventListener("click", function () {
        current = c.dataset.filter;
        chips.forEach(function (x) { x.setAttribute("aria-pressed", x === c ? "true" : "false"); });
        applyFilter();
      });
    });
    filter.addEventListener("input", applyFilter);
    document.querySelectorAll("tr.rowlink").forEach(function (tr) {
      tr.addEventListener("click", function (ev) {
        if (ev.target.closest("a")) return;
        location.href = tr.dataset.href;
      });
    });
    applyFilter();
  }

  var overlay = document.getElementById("overlay");
  if (!overlay) return;
  var rects = overlay.querySelectorAll("rect.blk");
  var all = document.getElementById("toggle-all");

  function applyToggles() {
    var on = {};
    document.querySelectorAll(".cls-toggle").forEach(function (c) { on[c.dataset.cls] = pressed(c); });
    overlay.style.display = pressed(all) ? "" : "none";
    rects.forEach(function (r) { r.style.display = on[r.dataset.cls] ? "" : "none"; });
  }
  document.querySelectorAll("#toggles .chip").forEach(function (c) {
    c.addEventListener("click", function () {
      c.setAttribute("aria-pressed", pressed(c) ? "false" : "true");
      applyToggles();
    });
  });

  var tip = document.getElementById("tip");
  rects.forEach(function (r) {
    r.addEventListener("mouseenter", function () {
      tip.textContent = "#" + r.dataset.order + " " + r.dataset.cls;
      tip.hidden = false;
    });
    r.addEventListener("mouseleave", function () { tip.hidden = true; });
    r.addEventListener("click", function () {
      var li = document.querySelector('.blocktext li[data-order="' + r.dataset.order + '"]');
      if (li) {
        li.closest("details").open = true;
        li.scrollIntoView({ block: "center" });
        li.classList.add("flash");
        setTimeout(function () { li.classList.remove("flash"); }, 1200);
      }
    });
  });

  function highlight(orders) {
    rects.forEach(function (r) { r.classList.toggle("hl", orders.indexOf(r.dataset.order) >= 0); });
    overlay.classList.toggle("dim", orders.length > 0);
  }
  document.querySelectorAll(".entry").forEach(function (li) {
    var orders = (li.dataset.orders || "").split(",").filter(Boolean);
    li.addEventListener("mouseenter", function () { highlight(orders); });
    li.addEventListener("mouseleave", function () { highlight([]); });
  });
})();
