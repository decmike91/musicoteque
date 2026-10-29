// Télécommande Musicothèque — fonctionne dans un navigateur ou dans l'application Android.
"use strict";
const $ = (s) => document.querySelector(s);
const el = (tag, cls, txt) => { const e = document.createElement(tag); if (cls) e.className = cls; if (txt != null) e.textContent = txt; return e; };
const fmt = (s) => { s = Math.max(0, Math.round(s || 0)); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`; };
const store = { get: (k, d) => { try { return localStorage.getItem(k) ?? d; } catch { return d; } },
                set: (k, v) => { try { localStorage.setItem(k, v); } catch {} },
                del: (k) => { try { localStorage.removeItem(k); } catch {} } };

let token = store.get("mt_token", "");
let src = parseInt(store.get("mt_src", "0"), 10) || 0;
let state = null, view = "play", seeking = false, lastCover = "", pollTimer = null;

// ------------------------------------------------------------------ API
async function api(path, body) {
  const opts = { headers: { "X-Token": token, "Content-Type": "application/json" } };
  if (body !== undefined) { opts.method = "POST"; opts.body = JSON.stringify(body); }
  const r = await fetch(path, opts);
  if (r.status === 401) { showPair(); throw new Error("non appairé"); }
  const data = await r.json();
  if (data && data.ok === false && data.message) toast(data.message);
  return data;
}
const cmd = (action, value) => api("/api/cmd", { src, action, value }).then(refresh).catch(() => {});

function toast(msg) {
  const t = $("#toast"); t.textContent = msg; t.classList.remove("hidden");
  clearTimeout(toast.t); toast.t = setTimeout(() => t.classList.add("hidden"), 2800);
}

// ------------------------------------------------------------------ appairage
let pin = "";
function showPair() {
  $("#main").classList.add("hidden"); $("#pair").classList.remove("hidden");
  clearInterval(pollTimer); pin = ""; drawDots();
}
function drawDots() { [...$("#dots").children].forEach((d, i) => d.classList.toggle("full", i < pin.length)); }
function buildKeypad() {
  const k = $("#keypad");
  ["1","2","3","4","5","6","7","8","9","⌫","0","OK"].forEach((c) => {
    const b = el("button", c === "OK" ? "primary" : "", c);
    b.onclick = () => {
      $("#pair-error").textContent = "";
      if (c === "⌫") pin = pin.slice(0, -1);
      else if (c === "OK") return doPair();
      else if (pin.length < 4) pin += c;
      drawDots();
      if (pin.length === 4) doPair();
    };
    k.appendChild(b);
  });
}
async function doPair() {
  if (pin.length !== 4) return;
  try {
    const r = await fetch("/api/pair", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pin, name: deviceName() }) });
    const d = await r.json();
    if (d.token) { token = d.token; store.set("mt_token", token); start(); }
    else { $("#pair-error").textContent = d.error || "Code refusé"; pin = ""; drawDots(); }
  } catch { $("#pair-error").textContent = "Musicothèque injoignable"; }
}
function deviceName() {
  const m = navigator.userAgent.match(/Android[^;]*;\s*([^;)]+)/);
  return m ? m[1].trim() : (navigator.platform || "Téléphone");
}

// ------------------------------------------------------------------ démarrage
async function start() {
  try {
    const h = await (await fetch("/api/hello", { headers: { "X-Token": token } })).json();
    if (!h.paired) return showPair();
  } catch { $("#offline").classList.remove("hidden"); setTimeout(start, 3000); return; }
  $("#pair").classList.add("hidden"); $("#main").classList.remove("hidden");
  if (window.MusicoApp) $("#b-forget").classList.remove("hidden");
  await refresh();
  clearInterval(pollTimer);
  pollTimer = setInterval(() => { if (!document.hidden) refresh(); }, 1000);
}

async function refresh() {
  try {
    state = await api("/api/state");
    $("#offline").classList.add("hidden");
  } catch (e) {
    if (String(e.message) !== "non appairé") $("#offline").classList.remove("hidden");
    return;
  }
  const used = state.sources.filter((s) => s.used);
  if (!used.some((s) => s.id === src)) { src = 0; store.set("mt_src", "0"); }
  drawSources(used);
  drawPlayer();
  if (view === "sound") drawOutputs();
  if (view === "queue" && state.sources[src].queue_pos !== drawQueue.pos) loadQueue();
}

function drawSources(used) {
  const box = $("#sources");
  box.classList.toggle("hidden", used.length < 2);
  const key = used.map((s) => s.id + s.label + s.playing).join("|") + src;
  if (box.dataset.key === key) return;
  box.dataset.key = key; box.innerHTML = "";
  used.forEach((s) => {
    const b = el("button", s.id === src ? "on" : "", (s.playing ? "▶ " : "") + s.label);
    b.onclick = () => { src = s.id; store.set("mt_src", String(src)); lastCover = ""; box.dataset.key = ""; refresh();
                        if (view === "queue") loadQueue(); };
    box.appendChild(b);
  });
}

// ------------------------------------------------------------------ lecture
function drawPlayer() {
  const s = state.sources[src];
  $("#np-title").textContent = s.title || "Aucun titre";
  $("#np-artist").textContent = s.title ? (s.artist || "Artiste inconnu") : "Choisissez de la musique (onglet Musique)";
  $("#np-album").textContent = [s.album, s.year].filter(Boolean).join(" · ");
  $("#b-play").textContent = s.playing ? "⏸" : "▶";
  $("#b-shuffle").classList.toggle("on", s.shuffle);
  $("#b-repeat").classList.toggle("on", s.repeat !== "none");
  $("#b-repeat").textContent = s.repeat === "one" ? "🔂" : "🔁";
  $("#b-mute").textContent = s.muted ? "🔇" : "🔊";
  if (!seeking) $("#seek").value = s.duration ? Math.round((s.position / s.duration) * 1000) : 0;
  $("#t-pos").textContent = fmt(s.position); $("#t-dur").textContent = fmt(s.duration);
  if (!drawPlayer.volBusy) { $("#vol").value = Math.round(s.volume * 100); $("#vol-lbl").textContent = Math.round(s.volume * 100) + " %"; }
  $("#where").textContent = "Lecture sur : " + s.label;
  if (s.path !== lastCover) {
    lastCover = s.path;
    const c = $("#cover");
    c.style.backgroundImage = ""; c.textContent = "♪";
    if (s.path && s.has_cover) {
      const img = new Image();
      img.onload = () => { c.style.backgroundImage = `url("${img.src}")`; c.textContent = ""; };
      img.src = `/api/cover?path=${encodeURIComponent(s.path)}&t=${encodeURIComponent(token)}`;
    }
  }
}

function bindPlayer() {
  $("#b-play").onclick = () => cmd("toggle");
  $("#b-next").onclick = () => cmd("next");
  $("#b-prev").onclick = () => cmd("prev");
  $("#b-shuffle").onclick = () => cmd("shuffle", !state.sources[src].shuffle);
  $("#b-repeat").onclick = () => cmd("repeat");
  $("#b-mute").onclick = () => cmd("mute", !state.sources[src].muted);
  const seek = $("#seek");
  seek.oninput = () => { seeking = true; const s = state.sources[src]; $("#t-pos").textContent = fmt(seek.value / 1000 * s.duration); };
  seek.onchange = () => { const s = state.sources[src]; cmd("seek", seek.value / 1000 * s.duration).finally(() => (seeking = false)); };
  const vol = $("#vol");
  let tv = null;
  vol.oninput = () => {
    drawPlayer.volBusy = true; $("#vol-lbl").textContent = vol.value + " %";
    clearTimeout(tv); tv = setTimeout(() => cmd("volume", vol.value / 100).finally(() => (drawPlayer.volBusy = false)), 150);
  };
}

// ------------------------------------------------------------------ musique
let libStack = [{ mode: "artists" }], libRows = [];
function bindLibrary() {
  $("#lib-seg").querySelectorAll("button").forEach((b) => (b.onclick = () => { $("#search").value = ""; libStack = [{ mode: b.dataset.mode }]; loadLib(); }));
  $("#lib-back").onclick = () => { if (libStack.length > 1) { libStack.pop(); loadLib(); } };
  let ts = null;
  $("#search").oninput = () => { clearTimeout(ts); ts = setTimeout(() => {
    const q = $("#search").value.trim();
    libStack = q ? [{ mode: "tracks", q }] : [{ mode: "artists" }]; loadLib(); }, 350); };
  $("#lib-playall").onclick = () => playPaths(libRows.map((r) => r.path), 0, "now");
}

async function loadLib() {
  const top = libStack[libStack.length - 1];
  $("#lib-seg").querySelectorAll("button").forEach((b) => b.classList.toggle("on", b.dataset.mode === libStack[0].mode));
  $("#lib-back").classList.toggle("hidden", libStack.length < 2);
  const list = $("#lib-list"); list.innerHTML = ""; libRows = [];
  $("#lib-playall").classList.add("hidden");
  const q = new URLSearchParams();
  try {
    if (top.mode === "artists") {
      const rows = await api("/api/library/artists");
      $("#lib-title").textContent = `${rows.length} artistes`;
      rows.forEach((a) => addRow(list, { t1: a.name, t2: `${a.albums} album${a.albums > 1 ? "s" : ""}`, icon: "👤",
        tap: () => { libStack.push({ mode: "albums", artist: a.name }); loadLib(); },
        more: () => groupSheet(a.name, { artist: a.name }) }));
    } else if (top.mode === "albums") {
      if (top.artist) q.set("artist", top.artist);
      const rows = await api("/api/library/albums?" + q);
      $("#lib-title").textContent = top.artist || `${rows.length} albums`;
      rows.forEach((a) => addRow(list, { t1: a.album, t2: [a.year, `${a.n} titres`].filter(Boolean).join(" · "), cover: a.cover,
        tap: () => { libStack.push({ mode: "tracks", artist: top.artist, album: a.album }); loadLib(); },
        more: () => groupSheet(a.album, { artist: top.artist, album: a.album }) }));
    } else if (top.mode === "playlists") {
      const rows = await api("/api/library/playlists");
      $("#lib-title").textContent = `${rows.length} playlists`;
      rows.forEach((p) => addRow(list, { t1: p.name, t2: `${p.n} titres`, icon: "📃",
        tap: () => { libStack.push({ mode: "tracks", playlist: p.id, title: p.name }); loadLib(); },
        more: () => groupSheet(p.name, { playlist: p.id }) }));
    } else {
      ["artist", "album", "playlist", "q"].forEach((k) => top[k] != null && top[k] !== undefined && q.set(k, top[k]));
      const rows = await api("/api/library/tracks?" + q);
      libRows = rows;
      $("#lib-title").textContent = (top.title || top.album || top.artist || (top.q ? `« ${top.q} »` : "Tous les titres")) + ` — ${rows.length}`;
      $("#lib-playall").classList.toggle("hidden", !rows.length);
      const cur = state && state.sources[src].path;
      rows.forEach((r, i) => addRow(list, { t1: (top.album && r.track ? `${r.track}. ` : "") + r.title,
        t2: [r.artist, top.album ? "" : r.album, fmt(r.duration)].filter(Boolean).join(" · "), cur: r.path === cur,
        tap: () => playPaths(rows.map((x) => x.path), i, "now"),
        more: () => trackSheet(r, rows, i) }));
    }
    if (!list.children.length) list.appendChild(el("li", "empty", "Rien ici pour l'instant"));
  } catch {}
}

function addRow(list, o) {
  const li = el("li", o.cur ? "cur" : "");
  const th = el("div", "thumb", o.icon || "♪");
  if (o.cover) { th.textContent = ""; th.style.backgroundImage = `url("/api/cover?path=${encodeURIComponent(o.cover)}&t=${encodeURIComponent(token)}")`; }
  const tx = el("div", "txt"); tx.append(el("div", "t1", o.t1), el("div", "t2", o.t2 || ""));
  const more = el("button", "more", "⋮"); more.onclick = (e) => { e.stopPropagation(); o.more && o.more(); };
  li.append(th, tx, more); li.onclick = o.tap;
  list.appendChild(li);
}

async function playPaths(paths, start = 0, mode = "now", target = src) {
  const r = await api("/api/play", { src: target, paths, start, mode }).catch(() => null);
  if (r && r.ok) {
    toast(mode === "now" ? "Lecture lancée" : mode === "next" ? "Sera joué ensuite" : "Ajouté à la file");
    if (mode === "now" && target === src) showView("play");
    refresh();
  }
}

function otherSources() { return state ? state.sources.filter((s) => s.used && s.id !== src) : []; }

function trackSheet(r, rows, i) {
  const acts = [["▶  Lire maintenant", () => playPaths(rows.map((x) => x.path), i, "now")],
                ["⏭  Lire ensuite", () => playPaths([r.path], 0, "next")],
                ["➕  Ajouter à la file", () => playPaths([r.path], 0, "add")]];
  otherSources().forEach((s) => acts.push([`🎧  Lire sur ${s.label}`, () => playPaths([r.path], 0, "now", s.id)]));
  sheet(r.title, acts);
}

async function groupSheet(title, filter) {
  const q = new URLSearchParams(); Object.entries(filter).forEach(([k, v]) => v != null && q.set(k, v));
  const get = async () => (await api("/api/library/tracks?" + q)).map((x) => x.path);
  const acts = [["▶  Tout lire", async () => playPaths(await get(), 0, "now")],
                ["🔀  Lire en aléatoire", async () => { await api("/api/cmd", { src, action: "shuffle", value: true }); playPaths(await get(), 0, "now"); }],
                ["➕  Ajouter à la file", async () => playPaths(await get(), 0, "add")]];
  otherSources().forEach((s) => acts.push([`🎧  Lire sur ${s.label}`, async () => playPaths(await get(), 0, "now", s.id)]));
  sheet(title, acts);
}

function sheet(title, actions) {
  const p = $("#sheet-panel"); p.innerHTML = ""; p.appendChild(el("h4", "", title));
  actions.forEach(([label, fn]) => { const b = el("button", "", label); b.onclick = () => { closeSheet(); fn(); }; p.appendChild(b); });
  const c = el("button", "", "Annuler"); c.onclick = closeSheet; p.appendChild(c);
  $("#sheet").classList.remove("hidden");
}
function closeSheet() { $("#sheet").classList.add("hidden"); }

// ------------------------------------------------------------------ file
async function loadQueue() {
  const d = await api("/api/queue?src=" + src).catch(() => null);
  if (!d) return;
  drawQueue.pos = d.pos;
  const list = $("#q-list"); list.innerHTML = "";
  $("#q-title").textContent = `File — ${d.items.length} titres`;
  d.items.forEach((it, k) => addRow(list, { t1: it.title, t2: [it.artist, fmt(it.duration)].filter(Boolean).join(" · "),
    icon: k === d.pos ? "▶" : String(k + 1), cur: k === d.pos, tap: () => cmd("play_at", k).then(loadQueue),
    more: () => sheet(it.title, [["▶  Lire", () => cmd("play_at", k).then(loadQueue)]]) }));
  if (!d.items.length) list.appendChild(el("li", "empty", "File vide : choisissez de la musique dans l'onglet Musique"));
  const cur = list.querySelector(".cur"); if (cur) cur.scrollIntoView({ block: "center" });
}
function drawQueue() {}

// ------------------------------------------------------------------ son
function drawOutputs() {
  const box = $("#outputs");
  const key = JSON.stringify(state.outputs.map((o) => [o.label, o.source, o.enabled, o.profile])) + state.profiles.join();
  if (box.dataset.key === key) {           // seulement les niveaux et volumes
    state.outputs.forEach((o) => {
      const c = box.querySelector(`[data-i="${o.index}"]`); if (!c) return;
      c.querySelector(".level i").style.width = Math.min(100, o.level * 100) + "%";
      const v = c.querySelector("input[type=range]"); if (!v.dataset.busy) v.value = Math.round(o.volume * 100);
    });
    return;
  }
  box.dataset.key = key; box.innerHTML = "";
  state.outputs.forEach((o) => {
    const c = el("div", "card"); c.dataset.i = o.index;
    const h = el("h4"); h.append(el("span", "", `${o.index + 1} · ${o.label}`));
    const sw = el("button", "switch" + (o.enabled ? " on" : ""), o.enabled ? "Active" : "Coupée");
    sw.onclick = () => setOutput(o.index, { enabled: !o.enabled });
    h.appendChild(sw); c.appendChild(h);
    const lv = el("div", "level"); lv.appendChild(el("i")); c.appendChild(lv);
    // volume
    const r1 = el("div", "row"); r1.appendChild(el("label", "", "Volume"));
    const vol = el("input"); vol.type = "range"; vol.min = 0; vol.max = 100; vol.value = Math.round(o.volume * 100);
    let t = null;
    vol.oninput = () => { vol.dataset.busy = "1"; clearTimeout(t); t = setTimeout(() => setOutput(o.index, { volume: vol.value / 100 }).finally(() => delete vol.dataset.busy), 150); };
    r1.appendChild(vol); c.appendChild(r1);
    // lecteur
    const r2 = el("div", "row"); r2.appendChild(el("label", "", "Lecteur"));
    const sel = el("select");
    state.source_names.forEach((n, i) => { const op = el("option", "", n); op.value = i; if (i === o.source) op.selected = true; sel.appendChild(op); });
    sel.onchange = () => setOutput(o.index, { source: parseInt(sel.value, 10) });
    r2.appendChild(sel); c.appendChild(r2);
    // profil
    const r3 = el("div", "row"); r3.appendChild(el("label", "", "Profil"));
    const ps = el("select");
    state.profiles.forEach((n) => { const op = el("option", "", n); op.value = n; if (n === o.profile) op.selected = true; ps.appendChild(op); });
    ps.onchange = () => setOutput(o.index, { profile: ps.value });
    r3.appendChild(ps); c.appendChild(r3);
    box.appendChild(c);
  });
}
const setOutput = (index, data) => api("/api/output", Object.assign({ index }, data)).then(refresh).catch(() => {});

// ------------------------------------------------------------------ navigation
function showView(v) {
  view = v;
  ["play", "lib", "queue", "sound"].forEach((k) => $("#v-" + k).classList.toggle("hidden", k !== v));
  document.querySelectorAll("nav button").forEach((b) => b.classList.toggle("on", b.dataset.view === v));
  if (v === "lib" && !$("#lib-list").children.length) loadLib();
  if (v === "queue") loadQueue();
  if (v === "sound" && state) { $("#outputs").dataset.key = ""; drawOutputs(); }
  $("main").scrollTop = 0;
}

document.querySelectorAll("nav button").forEach((b) => (b.onclick = () => showView(b.dataset.view)));
$("#sheet").onclick = (e) => { if (e.target.id === "sheet") closeSheet(); };
$("#q-shuffle").onclick = () => cmd("shuffle", true).then(loadQueue);
$("#q-clear").onclick = () => cmd("clear").then(loadQueue);
$("#b-logout").onclick = () => { store.del("mt_token"); token = ""; showPair(); };
$("#b-forget").onclick = () => { if (window.MusicoApp) window.MusicoApp.forget(); };
buildKeypad(); bindPlayer(); bindLibrary();
start();
