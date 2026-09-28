const CACHE_NAME = "ai-billing-v1";

const STATIC_FILES = [
    "/static/style.css",
    "/static/icons/icon-192.png",
    "/static/icons/icon-512.png"
];

self.addEventListener("install", function (event) {
    event.waitUntil(
        caches.open(CACHE_NAME).then(function (cache) {
            return cache.addAll(STATIC_FILES);
        })
    );
    self.skipWaiting();
});

self.addEventListener("activate", function (event) {
    event.waitUntil(
        caches.keys().then(function (names) {
            return Promise.all(
                names
                    .filter(function (name) { return name !== CACHE_NAME; })
                    .map(function (name) { return caches.delete(name); })
            );
        })
    );
    self.clients.claim();
});

self.addEventListener("fetch", function (event) {

    if (event.request.method !== "GET") {
        return;
    }

    const url = new URL(event.request.url);

    // Only cache static files. Pages (bills, reports) always come fresh from the server.
    if (url.pathname.startsWith("/static/")) {
        event.respondWith(
            caches.match(event.request).then(function (cached) {
                return cached || fetch(event.request);
            })
        );
    }
});