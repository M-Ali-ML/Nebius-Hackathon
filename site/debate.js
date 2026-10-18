// Time-travel debate: a chat replay of saved Hermes runs. No network calls; all data is inline.
(function () {
  const DATA = JSON.parse(document.getElementById("debate-data").textContent);
  const CITES = DATA.cites;
  const REDUCED = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const icon = (n) => `<svg><use href="#i-${n}"/></svg>`;
  const avatar = (role) => `<span class="avatar ${role}"><svg><use href="#av-${role === "wikipedian" ? "wiki" : role}"/></svg></span>`;
  const NAMES = { scholar: "The Scholar of 1790", wikipedian: "The Wikipedian", draw: "Draw" };
  const TYPING = { scholar: "dips the quill", wikipedian: "checks the sources", judge: "deliberates" };
  const TOOL_ICON = { search_sources: "search", get_pair: "file", view_scan: "image", find_drift: "search", view_neighbors: "image" };
  const fmt = (n) => (n == null ? "?" : n >= 1000 ? (n / 1000).toFixed(1) + "k" : String(n));

  let d = 0, shown = 0, playing = false, speed = 1, SPEEDS = [0.25, 0.5, 0.75, 1, 1.5, 2, 4], timer = null, token = 0;

  function debate() { return DATA.debates[d]; }

  // ---------- static parts ----------
  function renderTabs() {
    $("tabs").innerHTML = DATA.debates.map((x, i) => `
      <button class="dv-tab" role="tab" aria-selected="${i === d}" data-i="${i}">
        ${x.thumb ? `<img src="${x.thumb}" alt="Britannica scan row ${x.row}" loading="lazy">` : `<span class="ph"></span>`}
        <span><span class="k">${i + 1} · ${esc(x.entry_id)}</span><b>${esc(x.title)}</b><small>${esc(x.motion)}</small></span>
      </button>`).join("");
  }

  function renderBoard() {
    const x = debate(), s = x.stats;
    const n = s.claims || 1, pct = (k) => (100 * (s[k] || 0) / n).toFixed(1);
    $("board").innerHTML = `
      <div class="side left">${avatar("scholar")}<div class="who"><b>The Scholar of 1790</b><span>Britannica evidence only</span></div><span class="score" id="sc-scholar">0</span></div>
      <div class="mid"><div class="vs">THE MOTION</div><div class="motion">${esc(x.motion)}</div><div class="draws">draws: <span class="num" id="sc-draw">0</span></div></div>
      <div class="side right">${avatar("wikipedian")}<div class="who"><b>The Wikipedian</b><span>Wikipedia evidence only</span></div><span class="score" id="sc-wikipedian">0</span></div>
      <div class="stats">
        <span class="meter" title="verified: id resolves and every quote is in the source; cited: id resolves, no quote; unverified: id or quote fails">
          <span class="bar"><i class="v" style="width:${pct("verified")}%"></i><i class="c" style="width:${pct("cited")}%"></i><i class="u" style="width:${pct("unverified")}%"></i></span>
          <span><span class="num">${s.verified_share == null ? "?" : Math.round(100 * s.verified_share) + "%"}</span> verified quotes, <span class="num">${s.grounded_share == null ? "?" : Math.round(100 * s.grounded_share) + "%"}</span> grounded</span>
        </span>
        <span>${icon("check")} <span class="num">${s.verified ?? 0}</span> verified · <span class="num">${s.cited ?? 0}</span> cited · <span class="num">${s.unverified ?? 0}</span> unverified</span>
        <span>${icon("wrench")} <span class="num">${s.tool_calls}</span> tool calls</span>
        <span><span class="num">${fmt(s.tokens)}</span> tokens</span>
        <span><span class="num">${s.seconds}</span> s</span>
        <span><span class="num">${s.turns_ok}/${s.turns}</span> turns ok</span>
        <a class="src link small" href="#" title="saved transcript">${esc(x.file)}</a>
      </div>`;
    $("exhibits").innerHTML = `
      <a class="exhibit b" href="pages/${x.row}.html">${x.crop ? `<img src="${x.crop}" alt="Crop of the Britannica scan, row ${x.row}">` : ""}
        <span class="t"><small>Exhibit A · Britannica, scan row ${x.row}</small><b>${esc(x.entry_id)}</b></span></a>
      <a class="exhibit" href="${x.wiki_url || "#"}" target="_blank" rel="noopener"><span class="wlogo">W</span>
        <span class="t"><small>Exhibit B · Wikipedia today</small><b>${esc(x.wiki_title || "")}</b><span class="mono small muted">${esc(x.cite_w || "")}</span></span></a>`;
  }

  function decorateCites(root) {
    root.querySelectorAll("a.cite").forEach((a) => {
      const c = CITES[a.dataset.cite];
      a.classList.add(a.dataset.cite[0]);
      const st = a.dataset.st || (c ? c.status : "unverified");
      if (!c || !c.resolves || st === "unverified") a.classList.add("bad");
      else if (st === "verified") a.classList.add("ok");
      if (c && c.href) { a.href = c.href; if (c.kind === "W") { a.target = "_blank"; a.rel = "noopener"; } }
      a.tabIndex = 0;
    });
  }

  // ---------- steps ----------
  function checks(st) {
    const c = st.checks || {};
    return `<span class="checks" title="sentence checks"><span class="v">✓${c.verified || 0}</span><span class="c">•${c.cited || 0}</span><span class="u">!${c.unverified || 0}</span></span>`;
  }
  function trace(st) {
    if (!st.tools || !st.tools.length) return "";
    return `<details class="trace"><summary>${icon("wrench")} Tool trace (${st.tools.length})</summary><ol>${st.tools.map((t) =>
      `<li><code>${esc(t.name)}</code> ${esc(t.arg)} <span class="muted">→ ${esc(t.detail)}</span>${t.img ? `<img class="shot" src="${t.img}" alt="scan the agent read" loading="lazy">` : ""}</li>`).join("")}</ol></details>`;
  }
  function toolChips(st, live) {
    return (st.tools || []).map((t) => `<span class="tool ${t.error ? "err" : ""} ${live ? "run" : ""}">${t.img ? `<img src="${t.img}" alt="">` : icon(TOOL_ICON[t.name] || "wrench")}${esc(t.name)}</span>`).join("");
  }

  function stepEl(st, i) {
    const el = document.createElement("div");
    el.dataset.step = i;
    const meta = `<span class="meta">${st.seconds ?? "?"} s · ${fmt(st.tokens)} tok</span>`;
    const err = st.status !== "ok" ? `<div class="errbox">run failed: ${esc(st.error || "no reply")}</div>` : "";
    if (st.kind === "turn") {
      el.className = `turn ${st.role} ${st.status !== "ok" ? "failed" : ""}`;
      const head = `<div class="hd"><b>${esc(st.label)}</b><span class="pill gen">${esc(st.stage_label)}</span>${checks(st)}${meta}</div>`;
      const body = `<div class="tools"></div><div class="txt">${st.html}</div>${err}${trace(st)}`;
      el.innerHTML = st.role === "judge"
        ? `${avatar("judge")}<div class="bubble">${head}${body}</div>`
        : `${avatar(st.role)}<div class="bubble">${head}${body}</div>`;
      if (st.role === "judge") el.className = "judge-turn";
    } else if (st.kind === "point") {
      el.className = `card ${st.ruling}`;
      el.innerHTML = `<div class="hd">${avatar("judge")}<span>Point ${st.n}</span><span class="pill ${st.ruling}">${st.ruling}</span>
        <span class="win ${st.winner}">${st.winner === "scholar" ? "← " : ""}${NAMES[st.winner]}${st.winner === "wikipedian" ? " →" : ""}</span></div>
        <div class="tools"></div><div class="pt">${esc(st.point)}</div><div class="why txt">${st.html}</div>${trace(st)}`;
    } else {
      el.className = "final";
      el.innerHTML = `<div class="label">${icon("scale")} FINAL VERDICT · ${st.score.scholar} : ${st.score.wikipedian}${st.score.draw ? ` (${st.score.draw} draw)` : ""}</div>
        <div class="stamp ${st.winner}">${st.winner === "draw" ? "A draw" : NAMES[st.winner] + " wins"}</div>
        <div class="why txt">${st.html}</div>
        <ul>${(st.flags || []).map((f) => `<li class="flag">${icon("alert")}<span>${f}</span></li>`).join("")}
        ${(st.inferences || []).map((f) => `<li class="inf">💭 <span>${f}</span></li>`).join("")}</ul>`;
    }
    decorateCites(el);
    return el;
  }

  function setScore(st, animate) {
    const sc = st && st.score ? st.score : { scholar: 0, wikipedian: 0, draw: 0 };
    for (const k of ["scholar", "wikipedian", "draw"]) {
      const node = $("sc-" + k);
      if (!node) continue;
      if (node.textContent !== String(sc[k])) {
        node.textContent = sc[k];
        if (animate && !REDUCED && k !== "draw") { node.classList.remove("bump"); void node.offsetWidth; node.classList.add("bump"); }
      }
    }
  }
  function lastScore(n) {
    const steps = debate().steps;
    for (let i = n - 1; i >= 0; i--) if (steps[i].score) return steps[i];
    return null;
  }

  function renderUpTo(n) {
    token++;
    const arena = $("arena");
    arena.innerHTML = "";
    const steps = debate().steps;
    shown = Math.max(0, Math.min(n, steps.length));
    for (let i = 0; i < shown; i++) {
      const el = stepEl(steps[i], i);
      el.classList.add("done");
      el.querySelector(".tools") && (el.querySelector(".tools").innerHTML = toolChips(steps[i], false));
      el.style.animation = "none";
      arena.appendChild(el);
    }
    markGlow();
    setScore(lastScore(shown), false);
    updateControls();
  }

  function markGlow() {
    document.querySelectorAll(".glow").forEach((e) => e.classList.remove("glow"));
    const last = $("arena").lastElementChild;
    if (last) last.classList.add("glow");
  }

  const wait = (ms, t) => new Promise((res) => setTimeout(() => res(t === token), REDUCED ? 0 : ms / speed));

  function follow(el, smooth) {
    const r = el.getBoundingClientRect(), over = r.bottom - (innerHeight - 96);
    if (over > 0) scrollBy({ top: Math.min(over, Math.max(0, r.top - 64)), behavior: smooth && !REDUCED ? "smooth" : "auto" });
  }

  async function reveal() {
    const steps = debate().steps;
    if (shown >= steps.length) return false;
    const t = ++token;
    const st = steps[shown], i = shown;
    const el = stepEl(st, i);
    const txt = el.querySelector(".txt");
    const words = txt ? [...txt.querySelectorAll(".w")] : [];
    const tools = el.querySelector(".tools");
    let ind = null;
    if (txt) { ind = document.createElement("div"); ind.className = "typing"; ind.innerHTML = `<i></i><i></i><i></i> ${st.role === "judge" ? "the judge" : NAMES[st.role] || ""} ${TYPING[st.role] || ""}…`; txt.before(ind); }
    $("arena").appendChild(el);
    shown = i + 1;
    markGlow();
    updateControls();
    if (i > 0) follow(el, true);
    for (const tl of st.tools || []) {
      if (!tools) break;
      const span = document.createElement("span");
      span.innerHTML = toolChips({ tools: [tl] }, true);
      const chip = span.firstElementChild;
      tools.appendChild(chip);
      if (!(await wait(1100, t))) return false;
      chip.classList.remove("run");
      chip.querySelector("svg") && (chip.querySelector("svg").outerHTML = icon(tl.error ? "alert" : "check"));
    }
    if (!(await wait(st.kind === "turn" ? 1400 : 700, t))) return false;
    ind && ind.remove();
    if (st.kind === "final") fireConfetti(st.winner);
    for (let k = 0; k < words.length; k++) {
      words[k].classList.add("on", "cur");
      if (k) words[k - 1].classList.remove("cur");
      if (!(await wait(110, t))) return false;
      if (k % 12 === 0 && i > 0) follow(el, false);
    }
    words.length && words[words.length - 1].classList.remove("cur");
    el.classList.add("done");
    if (st.score) setScore(st, true);
    writeHash();
    return true;
  }

  async function play() {
    playing = true; updateControls();
    while (playing) {
      const ok = await reveal();
      if (!ok || !playing) break;
      if (!(await wait(2600, token))) break;
    }
    if (shown >= debate().steps.length) playing = false;
    updateControls();
  }
  function pause() { playing = false; token++; finishCurrent(); updateControls(); }
  function finishCurrent() {
    const last = $("arena").lastElementChild;
    if (last) { last.classList.add("done"); last.querySelectorAll(".typing").forEach((e) => e.remove()); last.querySelectorAll(".cur").forEach((e) => e.classList.remove("cur")); last.querySelectorAll(".tool.run").forEach((c) => c.classList.remove("run")); }
    setScore(lastScore(shown), false);
    writeHash();
  }

  function updateControls() {
    const n = debate().steps.length;
    $("stepnum").textContent = `${shown}/${n}`;
    document.querySelector(".ctl.play").innerHTML = icon(playing ? "pause" : "play");
    $("dots").innerHTML = debate().steps.map((s, i) => `<i class="${i < shown ? "on" : ""} ${i === shown - 1 ? "now" : ""}" data-i="${i + 1}" title="${esc(s.label)}: ${esc(s.kind === "point" ? "point " + s.n : s.stage_label)}"></i>`).join("");
    document.querySelectorAll(".dv-tab").forEach((b, i) => b.setAttribute("aria-selected", i === d));
  }

  function writeHash() {
    const h = `#${debate().slug}/${shown}`;
    if (location.hash !== h) history.replaceState(null, "", h);
  }
  function readHash() {
    const m = location.hash.match(/^#([\w-]+)(?:\/(\d+))?/);
    if (!m) return null;
    const i = DATA.debates.findIndex((x) => x.slug === m[1]);
    return i < 0 ? null : { i, n: m[2] == null ? 0 : +m[2] };
  }

  function select(i, n, autoplay) {
    playing = false; token++;
    d = i;
    renderBoard();
    renderUpTo(n);
    writeHash();
    if (autoplay) play();
  }

  const act = {
    toggle: () => (playing ? pause() : shown >= debate().steps.length ? (renderUpTo(0), play()) : play()),
    next: () => { if (playing) pause(); if (shown < debate().steps.length) { token++; renderUpTo(shown + 1); writeHash(); } },
    prev: () => { pause(); renderUpTo(shown - 1); writeHash(); },
    end: () => { pause(); renderUpTo(debate().steps.length); writeHash(); },
    restart: () => { pause(); renderUpTo(0); writeHash(); play(); },
    speed: (dir = 1) => { const i = SPEEDS.indexOf(speed); speed = SPEEDS[(i + dir + SPEEDS.length) % SPEEDS.length]; document.querySelector(".ctl.speed").textContent = speed + "x"; },
    share: () => { writeHash(); const url = location.href; (navigator.clipboard ? navigator.clipboard.writeText(url) : Promise.reject()).then(() => toast("Link to this step copied"), () => toast(url)); },
  };

  function toast(msg) {
    const t = $("toast"); t.textContent = msg; t.hidden = false;
    clearTimeout(t._h); t._h = setTimeout(() => (t.hidden = true), 1800);
  }

  // ---------- citation preview ----------
  const pop = $("pop");
  function showPop(a) {
    const c = CITES[a.dataset.cite];
    const id = a.dataset.cite;
    if (!c) { pop.innerHTML = `<div class="k">${icon("alert")} unknown id</div><b class="mono">${esc(id)}</b><p>This id does not resolve to a saved record.</p>`; }
    else {
      const status = !c.resolves ? "does not resolve" : a.dataset.st || c.status;
      pop.className = "dv-pop " + c.kind;
      pop.innerHTML = `<div class="k">${c.kind === "B" ? "📜 Britannica 1771-1797" : "🌐 Wikipedia today"} · <span class="pill ${status === "verified" ? "ok" : status === "cited" ? "renamed" : "bad"}">${esc(status)}</span></div>
        <b>${esc(c.title)}</b><span class="mono muted">${esc(id)} · ${esc(c.sub)}</span>
        ${c.img ? `<img src="${c.img}" alt="scan crop">` : ""}
        ${(c.quotes || []).slice(0, 2).map((q) => `<blockquote>“${esc(q)}”</blockquote>`).join("") || `<p class="muted" style="margin-top:6px">No checked quote for this id in the debate.</p>`}
        ${c.href ? `<span class="open">${icon("link")} ${c.kind === "B" ? "Open the page" : "Open this revision"}</span>` : ""}`;
    }
    pop.hidden = false;
    const r = a.getBoundingClientRect(), w = 320, h = pop.offsetHeight;
    let left = Math.min(Math.max(8, r.left + r.width / 2 - w / 2), innerWidth - w - 8);
    let top = r.top - h - 8;
    if (top < 56) top = r.bottom + 8;
    pop.style.left = left + "px"; pop.style.top = top + "px";
  }
  document.addEventListener("mouseover", (e) => { const a = e.target.closest("a.cite"); if (a) showPop(a); });
  document.addEventListener("mouseout", (e) => { if (e.target.closest("a.cite")) pop.hidden = true; });
  document.addEventListener("focusin", (e) => { const a = e.target.closest("a.cite"); if (a) showPop(a); else pop.hidden = true; });
  addEventListener("scroll", () => (pop.hidden = true), { passive: true });

  // ---------- confetti ----------
  function fireConfetti(winner) {
    if (REDUCED) return;
    const cv = $("confetti"), ctx = cv.getContext("2d");
    cv.width = innerWidth; cv.height = innerHeight;
    const colors = winner === "scholar" ? ["#c9b48c", "#8a6d3b", "#f5f1e8", "#ffd21e"] : winner === "wikipedian" ? ["#38bdf8", "#0369a1", "#bae6fd", "#ffd21e"] : ["#9ca3af", "#ffd21e", "#4ade80"];
    const parts = Array.from({ length: 140 }, () => ({ x: innerWidth / 2 + (Math.random() - .5) * 200, y: innerHeight * .55, vx: (Math.random() - .5) * 14, vy: -Math.random() * 14 - 6, r: Math.random() * 6 + 3, c: colors[Math.floor(Math.random() * colors.length)], a: Math.random() * 6, s: Math.random() * .3 - .15 }));
    let f = 0;
    (function tick() {
      ctx.clearRect(0, 0, cv.width, cv.height);
      for (const p of parts) { p.vy += .35; p.x += p.vx; p.y += p.vy; p.a += p.s; ctx.save(); ctx.translate(p.x, p.y); ctx.rotate(p.a); ctx.fillStyle = p.c; ctx.fillRect(-p.r, -p.r / 2, p.r * 2, p.r); ctx.restore(); }
      if (++f < 150) requestAnimationFrame(tick); else ctx.clearRect(0, 0, cv.width, cv.height);
    })();
  }

  // ---------- wiring ----------
  $("tabs").addEventListener("click", (e) => { const b = e.target.closest(".dv-tab"); if (b) select(+b.dataset.i, 0, true); });
  $("controls").addEventListener("click", (e) => {
    const b = e.target.closest("[data-act]"); if (b) return act[b.dataset.act]();
    const dot = e.target.closest(".ctl-dots i"); if (dot) { pause(); renderUpTo(+dot.dataset.i); writeHash(); }
  });
  document.addEventListener("keydown", (e) => {
    if (e.target.closest("input, textarea") || e.metaKey || e.ctrlKey || e.altKey) return;
    const k = e.key;
    if (k === " ") { e.preventDefault(); act.toggle(); }
    else if (k === "ArrowRight") act.next();
    else if (k === "ArrowLeft") act.prev();
    else if (k === "e" || k === "E") act.end();
    else if (k === "r" || k === "R") act.restart();
    else if (k === "s") act.speed(1);
    else if (k === "S") act.speed(-1);
    else if (/^[1-9]$/.test(k) && +k <= DATA.debates.length) select(+k - 1, 0, true);
  });
  addEventListener("hashchange", () => { const h = readHash(); if (h && (h.i !== d || h.n !== shown)) select(h.i, h.n, false); });

  renderTabs();
  const h = readHash();
  if (!DATA.debates.length) { $("arena").innerHTML = "<p class='muted'>No saved debates. Run scripts/debate.py run.</p>"; return; }
  if (h) select(h.i, h.n, h.n === 0); else select(0, 0, true);
})();
