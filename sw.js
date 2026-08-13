/* ============================================================
   AI 学习工作台 · Service Worker
   策略：静态资源 Cache First，页面 Network First 回退 Cache
   ============================================================ */

var CACHE_VERSION = 'ai-wb-v1';
var STATIC_CACHE = CACHE_VERSION + '-static';
var PAGE_CACHE = CACHE_VERSION + '-pages';

// 需要预缓存的静态资源
var PRECACHE_URLS = [
  './',
  './index.html',
  './models.html',
  './concepts.html',
  './skill.html',
  './mcp.html',
  './news.html',
  './comparison.html',
  './glossary.html',
  './manifest.json',
  './_shared/css/app.css',
  './_shared/js/app.js',
  './_shared/js/echarts.min.js',
  './assets/charts.js',
  './assets/icon-192.png',
  './assets/icon-512.png',
  './assets/ai-workbench.ico',
  './_shared/fonts/BricolageGrotesque-Regular.ttf',
  './_shared/fonts/BricolageGrotesque-Bold.ttf',
  './_shared/fonts/JetBrainsMono-Regular.ttf'
];

// 静态资源后缀（Cache First）
var STATIC_EXTS = ['.css', '.js', '.ttf', '.woff', '.woff2', '.png', '.ico', '.jpg', '.jpeg', '.svg'];

/* ---------- Install：预缓存 ---------- */
self.addEventListener('install', function (event) {
  event.waitUntil(
    caches.open(STATIC_CACHE).then(function (cache) {
      return cache.addAll(PRECACHE_URLS);
    }).then(function () {
      return self.skipWaiting();
    })
  );
});

/* ---------- Activate：清理旧缓存 ---------- */
self.addEventListener('activate', function (event) {
  event.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(
        keys.filter(function (key) {
          return key.indexOf(CACHE_VERSION) !== 0;
        }).map(function (key) {
          return caches.delete(key);
        })
      );
    }).then(function () {
      return self.clients.claim();
    })
  );
});

/* ---------- Fetch：分流策略 ---------- */
self.addEventListener('fetch', function (event) {
  var req = event.request;

  // 只处理 GET 请求
  if (req.method !== 'GET') return;

  var url = new URL(req.url);

  // 跳过跨域请求
  if (url.origin !== self.location.origin) return;

  // 判断是否静态资源
  var isStatic = STATIC_EXTS.some(function (ext) {
    return url.pathname.endsWith(ext);
  });

  // 静态资源：Cache First
  if (isStatic) {
    event.respondWith(
      caches.match(req).then(function (cached) {
        if (cached) {
          // 后台更新缓存
          fetch(req).then(function (res) {
            caches.open(STATIC_CACHE).then(function (cache) {
              cache.put(req, res.clone());
            });
          }).catch(function () {});
          return cached;
        }
        return fetch(req).then(function (res) {
          var clone = res.clone();
          caches.open(STATIC_CACHE).then(function (cache) {
            cache.put(req, clone);
          });
          return res;
        });
      })
    );
    return;
  }

  // HTML 页面：Network First，回退缓存
  event.respondWith(
    fetch(req).then(function (res) {
      var clone = res.clone();
      caches.open(PAGE_CACHE).then(function (cache) {
        cache.put(req, clone);
      });
      return res;
    }).catch(function () {
      return caches.match(req).then(function (cached) {
        if (cached) return cached;
        // 如果缓存也没有，返回首页
        return caches.match('./index.html');
      });
    })
  );
});

/* ---------- 接收消息：强制更新 ---------- */
self.addEventListener('message', function (event) {
  if (event.data === 'skipWaiting') {
    self.skipWaiting();
  }
});
