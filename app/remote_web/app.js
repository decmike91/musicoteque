// Musicothèque — télécommande (navigateur du téléphone ou application Android)
"use strict";
const $ = (id) => document.getElementById(id);
let token = localStorage.getItem("mt_token") || "";
let src = parseInt(localStorage.getItem("mt_src") || "0", 10);
let state = null, view = "play", dragging = false;
let lib = { kind: "artists", stack: [], rows: [] };

// ------------------------------------------------------------------ réseau
async function api(path, body) {
  const opt = { headers: { "X-Token": token } };
  if (body !== undefined) {
    opt.method = "POST"; opt.body = JSON.stringify(body);
    opt.headers["Content-Type"] = "application/json";
  }
  const r = await fetch("/api/" + path, opt);
  if (r.status === 401) { showPair(); throw new Error("non appairé"); }
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || ("erreur " + r.status));
  return j;
}
const cmd = (action, value) => api("cmd", { src, action, value }).then(refresh).catch((e) => toast(e.message));

function toast(msg, ms = 2600) {
  const t = $("toast"); t.textContent = msg; t.classList.remove("hidden");
  clearTimeout(t._h); t._h = setTimeout(() => t.classList.add("hidden"), ms);
}
const fmt = (s) => { s = Math.max(0, Math.round(s || 0)); return Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0"); };
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

// ------------------------------------------------------------------ appairage
function showPair() {
  $("main").classList.add("hidden"); $("pair").classList.remove("hidden");
}
async function pair(pin) {
  $("pairErr").textContent = "";
  try {
    const r = await fetch("/api/pair", { method: "POST", headers: { "Content-Type": "application/json" },
                                         body: JSON.stringify({ pin }) });
    const j = await r.json();
    if (!r.ok) { $("pairErr").textContent = j.error || "Code refusé"; return; }
    token = j.token; localStorage.setItem("mt_token", token);
    start();
  } catch (e) { $("pairErr").textContent = "Raspberry Pi injoignable : même réseau Wi-Fi ?"; }
}
$("pairBtn").onclick = () => pair($("pin").value);
$("pin").addEventListener("input", (e) => { if (e.target.value.length === 4) pair(e.target.value); });

// ------------------------------------------------------------------ navigation
document.querySelectorAll("footer button").forEach((b) => b.onclick = () => show(b.dataset.v));
function show(v) {
  view = v;
  document.querySelectorAll("footer button").forEach((b) => b.classList.toggle("on", b.dataset.v === v));
  ["play", "lib", "queue", "sound"].forEach((k) => $("v-" + k).classList.toggle("hidden", k !== v));
  if (v === "lib" && !lib.rows.length) loadLib();
  if (v === "queue") loadQueue();
  if (v === "sound") renderOutputs();
}

// ------------------------------------------------------------------ état
async function refresh() {
  try {
    state = await api("state");
    $("conn").className = "dot ok";
    render();
  } catch (e) { $("conn").className = "dot bad"; }
}
function cur() { return state && state.sources[src]; }

function render() {
  if (!state) return;
  if (!state.used.includes(src)) src = 0;
  // choix du lecteur
  const chips = $("players");
  chips.classList.toggle("hidden", state.used.length < 2);
  chips.innerHTML = state.used.map((i) => {
    const s = state.sources[i];
    return `<button data-i="${i}" class="${i === src ? "on" : ""}">${s.playing ? "▶ " : ""}${esc(s.label)}</button>`;
  }).join("");
  chips.querySelectorAll("button").forEach((b) => b.onclick = () => {
    src = +b.dataset.i; localStorage.setItem("mt_src", src); render(); if (view === "queue") loadQueue();
  });
  const s = cur();
  $("title").textContent = s.title || "Aucun titre";
  $("artist").textContent = s.artist || (s.path ? "" : "Choisissez de la musique dans l'onglet Musique");
  $("album").textContent = [s.album, s.year].filter(Boolean).join(" · ");
  const img = $("cover");
  const want = s.has_cover ? `/api/cover?t=${encodeURIComponent(token)}&path=${encodeURIComponent(s.path)}` : "";
  if (img.dataset.src !== want) {
    img.dataset.src = want;
    if (want) { img.src = want; img.style.display = "block"; $("coverPh").style.display = "none"; }
    else { img.removeAttribute("src"); img.style.display = "none"; $("coverPh").style.display = "flex"; }
  }
  if (!dragging) {
    $("seek").value = s.duration ? Math.round(s.position / s.duration * 1000) : 0;
    $("vol").value = Math.round(s.volume * 100); $("volLbl").textContent = Math.round(s.volume * 100) + " %";
  }
  $("tpos").textContent = fmt(s.position); $("tdur").textContent = fmt(s.duration);
  $("bPlay").textContent = s.playing ? "⏸" : "▶";
  $("bShuffle").classList.toggle("on", s.shuffle);
  $("bRepeat").classList.toggle("on", s.repeat !== "none");
  $("bRepeat").textContent = s.repeat === "one" ? "🔂" : "🔁";
  $("bMute").textContent = s.muted ? "🔇" : "🔊";
  $("qTitle").textContent = (state.used.length > 1 ? s.short + " — " : "File — ") + s.queue_len + " titres";
  if (view === "sound" && !document.activeElement.closest?.(".out")) renderOutputs();
}

// ------------------------------------------------------------------ commandes lecture
$("bPlay").onclick = () => cmd("play_pause");
$("bNext").onclick = () => cmd("next");
$("bPrev").onclick = () => cmd("prev");
$("bShuffle").onclick = () => cmd("shuffle", !cur().shuffle);
$("bRepeat").onclick = () => cmd("repeat");
$("bMute").onclick = () => cmd("mute");
for (const id of ["seek", "vol"]) {
  const el = $(id);
  el.addEventListener("pointerdown", () => dragging = true);
  el.addEventListener("touchstart", () => dragging = true, { passive: true });
}
$("seek").addEventListener("change", (e) => { dragging = false; const s = cur(); if (s.duration) cmd("seek", e.target.value / 1000 * s.duration); });
$("vol").addEventListener("input", (e) => {
  $("volLbl").textContent = e.target.value + " %";
  clearTimeout($("vol")._h); $("vol")._h = setTimeout(() => cmd("volume", e.target.value / 100), 120);
});
$("vol").addEventListener("change", () => dragging = false);

// ------------------------------------------------------------------ bibliothèque
document.querySelectorAll("#libSeg button").forEach((b) => b.onclick = () => {
  document.querySelectorAll("#libSeg button").forEach((x) => x.classList.toggle("on", x === b));
  lib.kind = b.dataset.k; lib.stack = []; $("q").value = ""; loadLib();
});
let qTimer;
$("q").addEventListener("input", () => { clearTimeout(qTimer); qTimer = setTimeout(() => {
  lib.stack = $("q").value ? [{ kind: "tracks", q: $("q").value, title: "« " + $("q").value + " »" }] : []; loadLib(); }, 350); });
$("back").onclick = () => { lib.stack.pop(); loadLib(); };

async function loadLib() {
  const top = lib.stack[lib.stack.length - 1] || { kind: lib.kind, title: "" };
  const p = new URLSearchParams({ kind: top.kind });
  for (const k of ["artist", "album", "q", "id"]) if (top[k] != null) p.set(k, top[k]);
  $("back").classList.toggle("hidden", !lib.stack.length);
  $("list").innerHTML = `<li class="empty">Chargement…</li>`;
  let rows;
  try { rows = await api("library?" + p.toString()); } catch (e) { $("list").innerHTML = `<li class="empty">${esc(e.message)}</li>`; return; }
  lib.rows = rows; lib.top = top;
  const isTracks = top.kind === "tracks" || top.kind === "playlist";
  $("playAll").classList.toggle("hidden", !isTracks || !rows.length);
  $("shufAll").classList.toggle("hidden", !isTracks || !rows.length);
  $("crumb").textContent = top.title || ({ artists: "Artistes", albums: "Albums", tracks: "Titres", playlists: "Playlists" }[top.kind]) + ` (${rows.length})`;
  if (!rows.length) { $("list").innerHTML = `<li class="empty">Rien ici.</li>`; return; }
  const curPath = cur() && cur().path;
  $("list").innerHTML = rows.map((r, i) => {
    if (top.kind === "artists") return `<li data-i="${i}"><div class="t"><b>${esc(r.name)}</b><small>${r.albums} album(s)</small></div><span class="dim">›</span></li>`;
    if (top.kind === "albums") return `<li data-i="${i}"><div class="t"><b>${esc(r.name)}</b><small>${[r.year, r.count + " titres"].filter(Boolean).join(" · ")}</small></div><span class="dim">›</span></li>`;
    if (top.kind === "playlists") return `<li data-i="${i}"><div class="t"><b>${esc(r.name)}</b><small>${r.count} titres</small></div><span class="dim">›</span></li>`;
    const sub = [r.artist, top.album ? "" : r.album, fmt(r.duration)].filter(Boolean).join(" · ");
    return `<li data-i="${i}" class="${r.path === curPath ? "cur" : ""}"><div class="t"><b>${top.album && r.track ? r.track + ". " : ""}${esc(r.title)}</b><small>${esc(sub)}</small></div><button class="more" data-m="${i}">⋮</button></li>`;
  }).join("");
  $("list").querySelectorAll("li[data-i]").forEach((li) => li.onclick = (e) => {
    const i = +li.dataset.i, r = rows[i];
    if (e.target.dataset.m != null) return trackMenu(r);
    if (top.kind === "artists") lib.stack.push({ kind: "albums", artist: r.name, title: r.name });
    else if (top.kind === "albums") lib.stack.push({ kind: "tracks", artist: r.artist ?? undefined, album: r.name, title: r.name });
    else if (top.kind === "playlists") lib.stack.push({ kind: "playlist", id: r.id, title: r.name });
    else return playList(rows.map((x) => x.path), i, "now");
    loadLib();
  });
}
function playList(paths, start, mode) {
  api("play", { src, paths, start, mode })
    .then(() => { toast(mode === "now" ? "Lecture lancée" : mode === "next" ? "Sera lu ensuite" : "Ajouté à la file");
                  if (mode === "now") show("play"); refresh(); })
    .catch((e) => toast(e.message));
}
$("playAll").onclick = () => playList(lib.rows.map((r) => r.path), 0, "now");
$("shufAll").onclick = async () => { await api("cmd", { src, action: "shuffle", value: true }).catch(() => {}); playList(lib.rows.map((r) => r.path), 0, "now"); };

function trackMenu(r) {
  const others = (state ? state.used : []).filter((i) => i !== src);
  const acts = [["▶  Lire maintenant", () => playList([r.path], 0, "now")],
                ["⏭  Lire ensuite", () => playList([r.path], 0, "next")],
                ["➕  Ajouter à la file", () => playList([r.path], 0, "add")]];
  for (const i of others) acts.push([`🎧  Lire sur ${state.sources[i].label}`,
    () => api("play", { src: i, paths: [r.path], mode: "now" }).then(() => toast("Lancé sur " + state.sources[i].short))]);
  sheet(r.title, acts);
}
function sheet(title, acts) {
  $("sheetTitle").textContent = title;
  $("sheetBtns").innerHTML = "";
  acts.forEach(([label, fn]) => {
    const b = document.createElement("button"); b.textContent = label;
    b.onclick = () => { $("sheet").classList.add("hidden"); fn(); };
    $("sheetBtns").appendChild(b);
  });
  $("sheet").classList.remove("hidden");
}
$("sheetCancel").onclick = () => $("sheet").classList.add("hidden");
$("sheet").onclick = (e) => { if (e.target.id === "sheet") $("sheet").classList.add("hidden"); };

// ------------------------------------------------------------------ file
async function loadQueue() {
  let rows;
  try { rows = await api("queue?src=" + src); } catch (e) { return; }
  $("qlist").innerHTML = rows.length ? rows.map((r) => `<li data-k="${r.k}" class="${r.current ? "cur" : ""}"><div class="t"><b>${r.current ? "▶ " : ""}${esc(r.title)}</b><small>${esc(r.artist)}</small></div></li>`).join("")
                                     : `<li class="empty">La file est vide.</li>`;
  $("qlist").querySelectorAll("li[data-k]").forEach((li) => li.onclick = () => cmd("jump", +li.dataset.k).then(loadQueue));
}
$("qClear").onclick = () => cmd("clear").then(loadQueue);

// ------------------------------------------------------------------ sorties
const PLAYERS = ["Lecteur principal", "Lecteur 2", "Lecteur 3"];
function renderOutputs() {
  if (!state) return;
  $("outs").innerHTML = state.outputs.map((o) => `
    <div class="out" data-i="${o.index}">
      <div class="head"><span>${o.index + 1} · ${esc(o.label)}</span>
        <button class="switch ${o.enabled ? "on" : ""}" data-a="enabled">${o.enabled ? "Active" : "Coupée"}</button></div>
      <label>Musique diffusée</label>
      <select data-a="source">${PLAYERS.map((n, i) => `<option value="${i}" ${i === o.source ? "selected" : ""}>${n}</option>`).join("")}</select>
      <label>Volume de cette sortie : <span>${Math.round(o.volume * 100)} %</span></label>
      <input type="range" min="0" max="100" value="${Math.round(o.volume * 100)}" data-a="volume">
      <label>Profil audio</label>
      <select data-a="profile">${state.profiles.map((p) => `<option ${p === o.profile ? "selected" : ""}>${esc(p)}</option>`).join("")}</select>
    </div>`).join("");
  $("outs").querySelectorAll(".out").forEach((card) => {
    const index = +card.dataset.i, o = state.outputs[index];
    const send = (d) => api("output", Object.assign({ index }, d)).then(refresh).catch((e) => toast(e.message));
    card.querySelector('[data-a="enabled"]').onclick = () => send({ enabled: !o.enabled });
    card.querySelector('[data-a="source"]').onchange = (e) => send({ source: +e.target.value });
    card.querySelector('[data-a="profile"]').onchange = (e) => send({ profile: e.target.value });
    const v = card.querySelector('[data-a="volume"]');
    v.oninput = (e) => { card.querySelector("label span").textContent = e.target.value + " %";
      clearTimeout(v._h); v._h = setTimeout(() => send({ volume: e.target.value / 100 }), 150); };
  });
}

// ------------------------------------------------------------------ démarrage
let poll;
function start() {
  $("pair").classList.add("hidden"); $("main").classList.remove("hidden");
  refresh(); clearInterval(poll);
  poll = setInterval(() => { if (document.visibilityState === "visible") { refresh(); if (view === "queue") loadQueue(); } }, 1000);
}
(function init() {
  const m = location.hash.match(/pin=(\d{4})/);             // QR code : …/#pin=1234
  if (m && !token) { history.replaceState(null, "", "/"); return pair(m[1]); }
  if (token) start(); else showPair();
})();
if ("serviceWorker" in navigator && window.isSecureContext) navigator.serviceWorker.register("sw.js").catch(() => {});
