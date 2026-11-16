// Service Worker for Share COC PWA
const CACHE_NAME = 'share-coc-v10';
const ASSETS_TO_CACHE = [
  '/',
  '/files',
  '/manifest.json',
  '/logo.png',
  '/icon-192.png',
  '/icon-512.png',
  '/apple-touch-icon.png'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(ASSETS_TO_CACHE).catch(() => {});
    })
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.map((key) => {
          if (key !== CACHE_NAME) {
            return caches.delete(key);
          }
        })
      );
    })
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') return;
  let url;
  try {
    url = new URL(event.request.url);
  } catch {
    return;
  }
  const lowerPath = url.pathname.toLowerCase();
  if (
    url.origin !== self.location.origin ||
    url.hostname === '127.0.0.1' ||
    url.hostname === 'localhost' ||
    lowerPath.startsWith('/api/') ||
    lowerPath.endsWith('.exe') ||
    lowerPath.endsWith('.apk') ||
    lowerPath.endsWith('.reg')
  ) {
    return;
  }
  // Network first, fallback to cache
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        return response;
      })
      .catch(() => {
        return caches.match(event.request).then((cached) => cached || Response.error());
      })
  );
});
