/* SectorScope service worker
 * Bump VERSION on every deploy that changes the shell.
 * Rules:
 *   - Never cache API / auth / admin / non-GET / cross-origin.
 *   - Navigations: network-first, fall back to cached shell, then offline page.
 *   - Static assets (.css/.js/.png/...): stale-while-revalidate, keyed by full
 *     URL so ?v= cache-busting produces a fresh entry automatically.
 */

const VERSION = 'ss-v1';
const SHELL_CACHE = `shell-${VERSION}`;
const RUNTIME_CACHE = `runtime-${VERSION}`;
const OFFLINE_URL = '/offline.html';

const PRECACHE_URLS = [
  '/',
  OFFLINE_URL,
  '/assets/icon-192.png',
  '/assets/icon-512.png'
];

// Anything matching these is never touched by the cache.
// The worker API is on a different origin, so it is already excluded by the
// cross-origin bypass in isBypassed(). These are a guard for anything ever
// proxied same-origin.
const NEVER_CACHE_PREFIXES = [
  '/api/', '/auth/', '/admin/', '/digest', '/unsubscribe', '/razorpay', '/webhook'
];

const STATIC_EXT = /\.(?:css|js|mjs|png|jpg|jpeg|gif|svg|webp|ico|woff2?|ttf|json|webmanifest)$/i;

const NAV_TIMEOUT_MS = 4000;

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(SHELL_CACHE)
      .then((cache) => cache.addAll(PRECACHE_URLS))
      .catch(() => { /* a missing precache entry must not block install */ })
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(
      keys
        .filter((k) => k !== SHELL_CACHE && k !== RUNTIME_CACHE)
        .map((k) => caches.delete(k))
    );
    if (self.registration.navigationPreload) {
      try { await self.registration.navigationPreload.enable(); } catch (e) { /* noop */ }
    }
    await self.clients.claim();
  })());
});

self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') self.skipWaiting();
});

function isBypassed(request, url) {
  if (request.method !== 'GET') return true;
  if (url.origin !== self.location.origin) return true;
  if (url.search.includes('token=') || url.search.includes('key=')) return true;
  if (request.headers.has('Authorization')) return true;
  if (request.headers.get('Cache-Control') === 'no-store') return true;
  return NEVER_CACHE_PREFIXES.some((p) => url.pathname.startsWith(p));
}

async function handleNavigation(event) {
  const cache = await caches.open(SHELL_CACHE);
  try {
    const preload = await event.preloadResponse;
    if (preload) {
      cache.put('/', preload.clone()).catch(() => {});
      return preload;
    }
    const network = await Promise.race([
      fetch(event.request),
      new Promise((_, reject) =>
        setTimeout(() => reject(new Error('nav-timeout')), NAV_TIMEOUT_MS))
    ]);
    if (network && network.ok) cache.put('/', network.clone()).catch(() => {});
    return network;
  } catch (err) {
    const cachedShell = await cache.match('/');
    if (cachedShell) return cachedShell;
    const offline = await cache.match(OFFLINE_URL);
    if (offline) return offline;
    return new Response('Offline', {
      status: 503,
      headers: { 'Content-Type': 'text/plain' }
    });
  }
}

async function handleStatic(request) {
  const cache = await caches.open(RUNTIME_CACHE);
  const cached = await cache.match(request);
  const network = fetch(request)
    .then((response) => {
      if (response && response.ok && response.type === 'basic') {
        cache.put(request, response.clone()).catch(() => {});
      }
      return response;
    })
    .catch(() => null);

  if (cached) return cached;
  const fresh = await network;
  if (fresh) return fresh;
  return new Response('', { status: 504, statusText: 'Offline' });
}

self.addEventListener('fetch', (event) => {
  const request = event.request;
  const url = new URL(request.url);

  if (request.mode === 'navigate') {
    event.respondWith(handleNavigation(event));
    return;
  }

  if (isBypassed(request, url)) return;

  if (STATIC_EXT.test(url.pathname)) {
    event.respondWith(handleStatic(request));
  }
});
