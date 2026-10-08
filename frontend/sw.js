const CACHE_NAME = 'sistema-pos-pwa-v1';
const STATIC_ASSETS = [
  './',
  './index.html',
  './manifest.json',
  './css/variables.css',
  './css/layout.css',
  './css/components.css',
  './js/db.js',
  './js/api.js',
  './js/sync.js',
  './js/app.js',
  './assets/icon.svg'
];

// Instalación: Cachear App Shell
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      console.log('[SW] Pre-cacheando App Shell de SISTEMA POS PWA...');
      return cache.addAll(STATIC_ASSETS);
    }).then(() => self.skipWaiting())
  );
});

// Activación: Limpieza de cachés antiguas
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.map((key) => {
          if (key !== CACHE_NAME) {
            console.log('[SW] Eliminando caché obsoleta:', key);
            return caches.delete(key);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

// Estrategia Fetch:
// - Para recursos estáticos: Cache-First con actualización en segundo plano
// - Para llamadas de API (/api/): Network-First
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // Excluir llamadas de sincronización y mutación directa de API
  if (url.pathname.includes('/api/')) {
    event.respondWith(
      fetch(event.request).catch(() => {
        // En caso de corte de red, devolver respuesta JSON simulada offline
        return new Response(JSON.stringify({
          offline: true,
          message: 'Sin conexión a internet. La operación se procesará mediante IndexedDB local.'
        }), {
          headers: { 'Content-Type': 'application/json' },
          status: 503
        });
      })
    );
    return;
  }

  // Para estáticos: Stale-While-Revalidate
  event.respondWith(
    caches.match(event.request).then((cachedResponse) => {
      const fetchPromise = fetch(event.request).then((networkResponse) => {
        if (networkResponse && networkResponse.status === 200) {
          const responseToCache = networkResponse.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(event.request, responseToCache);
          });
        }
        return networkResponse;
      }).catch(() => cachedResponse);

      return cachedResponse || fetchPromise;
    })
  );
});

// Escucha de mensajes desde la app (ej: forzar actualización de caché)
self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
});
