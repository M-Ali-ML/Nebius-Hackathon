// Small helpers: filter the page list, toggle bbox classes, link entries to their blocks.
(function () {
  var filter = document.getElementById("filter");
  if (filter) {
    filter.addEventListener("input", function () {
      var q = filter.value.toLowerCase();
      document.querySelectorAll("#pages tbody tr").forEach(function (tr) {
        tr.style.display = tr.dataset.search.indexOf(q) >= 0 ? "" : "none";
      });
    });
  }

  var overlay = document.getElementById("overlay");
  if (!overlay) return;
  var rects = overlay.querySelectorAll("rect.blk");

  function applyToggles() {
    var all = document.getElementById("toggle-all").checked;
    var on = {};
    document.querySelectorAll(".cls-toggle").forEach(function (c) { on[c.value] = c.checked; });
    overlay.style.display = all ? "" : "none";
    rects.forEach(function (r) { r.style.display = on[r.dataset.cls] ? "" : "none"; });
  }
  document.querySelectorAll("#toggles input").forEach(function (c) { c.addEventListener("change", applyToggles); });

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
