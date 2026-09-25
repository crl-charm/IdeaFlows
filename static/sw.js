"use strict";

const CACHE_NAME = "ideaflow-shell-v1";
const OFFLINE_URL = "/static/offline.html";
const PRECACHE_URLS = [
  "/manifest.webmanifest",
  OFFLINE_URL,
  "/static/icons/apple-touch-icon.png",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png",
  "/static/icons/icon-maskable-192.png",
  "/static/icons/icon-maskable-512.png",
  "/static/css/pwa-install.css",
  "/static/js/pwa-install.js"
];
const PRECACHE_PATHS = new Set(PRECACHE_URLS);
const NETWORK_ONLY_PREFIXES = [
  "/api/",
  "/socket.io/",
  "/admin",
  "/dashboard",
  "/profile",
  "/login",
  "/logout",
  "/register",
  "/orders",
  "/order/",
  "/menu",
  "/inventory",
  "/expenses-view",
  "/receivables-view",
  "/boardroom",
  "/lounge-booking",
  "/checkout-records",
  "/daily-sales",
  "/receipt/",
  "/static/uploads/"
];

self.addEventListener("install", function (event) {
  event.waitUntil(precache());
});

async function precache() {
  const cache = await caches.open(CACHE_NAME);
  await Promise.all(PRECACHE_URLS.map(async function (path) {
    const response = await fetch(path, { cache: "reload" });
    if (!response.ok) throw new Error("Unable to precache IdeaFlow shell");
    const cacheControl = response.headers.get("Cache-Control") || "";
    if (!/\bno-store\b/i.test(cacheControl)) {
      await cache.put(path, response);
    }
  }));
}

self.addEventListener("activate", function (event) {
  event.waitUntil(caches.keys().then(function (names) {
    return Promise.all(names.map(function (name) {
      if (name.startsWith("ideaflow-") && name !== CACHE_NAME) {
        return caches.delete(name);
      }
      return undefined;
    }));
  }).then(function () {
    return self.clients.claim();
  }));
});

self.addEventListener("message", function (event) {
  if (event.data && event.data.type === "SKIP_WAITING") {
    event.waitUntil(self.skipWaiting());
  }
});

self.addEventListener("fetch", function (event) {
  const request = event.request;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  if (request.mode === "navigate") {
    event.respondWith(fetch(request).catch(function () {
      return caches.match(OFFLINE_URL);
    }));
    return;
  }

  if (NETWORK_ONLY_PREFIXES.some(function (prefix) {
    return url.pathname.startsWith(prefix);
  })) return;

  if (PRECACHE_PATHS.has(url.pathname)) {
    event.respondWith(caches.match(request, { ignoreSearch: true }).then(function (cached) {
      return cached || fetch(request);
    }));
  }
});
