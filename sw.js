// Mines Map service worker: app shell + map images cached for offline use; live data always from the network.
const V = "minesmap-v2";
const SHELL = ["./", "index.html", "manifest.webmanifest", "icons/icon-192.png", "tiles/terrain.jpg", "tiles/satellite.jpg", "tiles/topo.jpg"];
self.addEventListener("install", e => { e.waitUntil(caches.open(V).then(c => c.addAll(SHELL)).then(() => self.skipWaiting())); });
self.addEventListener("activate", e => { e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== V).map(k => caches.delete(k)))).then(() => self.clients.claim())); });
self.addEventListener("fetch", e => {
  const u = new URL(e.request.url);
  if (e.request.method !== "GET") return;
  if (u.pathname.includes("/data/") || u.pathname.endsWith(".json")) {            // live data: network first, last copy if offline
    e.respondWith(fetch(e.request).then(r => { const c = r.clone(); caches.open(V).then(x => x.put(u.pathname, c)); return r; }).catch(() => caches.match(u.pathname)));
    return;
  }
  if (e.request.mode === "navigate" || u.pathname.endsWith(".html")) {   // page: network first so updates show
    e.respondWith(fetch(e.request).then(r => { const c = r.clone(); caches.open(V).then(x => x.put(e.request, c)); return r; }).catch(() => caches.match(e.request).then(r => r || caches.match("index.html"))));
    return;
  }
  e.respondWith(caches.match(e.request).then(hit => hit || fetch(e.request).then(r => {   // images, scripts, fonts: cache first
    if (r.ok && (u.origin === location.origin || /cdnjs|gstatic|googleapis/.test(u.host))) { const c = r.clone(); caches.open(V).then(x => x.put(e.request, c)); }
    return r;
  })));
});
