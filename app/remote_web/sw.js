// Service worker minimal (utilisé seulement en HTTPS) : garde l'interface en cache.
const C = "mt-v1", FILES = ["/", "index.html", "style.css", "app.js", "icon-192.png"];
self.addEventListener("install", (e) => e.waitUntil(caches.open(C).then((c) => c.addAll(FILES))));
self.addEventListener("fetch", (e) => {
  if (e.request.url.includes("/api/")) return;
  e.respondWith(fetch(e.request).catch(() => caches.match(e.request)));
});
