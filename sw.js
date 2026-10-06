/* AI 学习工作台：Network First，离线回退缓存。
 * 导航请求使用 no-cache；激活时清理旧缓存并接管页面。
 * 递增缓存版本以分发共享脚本；DeepSeek 接入已停用，历史说明见项目记录。 */
var CACHE_VERSION = 'ai-wb-v34';
var STATIC_CACHE = CACHE_VERSION + '-static';
var PAGE_CACHE = CACHE_VERSION + '-pages';

// 需要预缓存的资源
var PRECACHE_URLS = [
  './',
  './index.html',
  './models.html',
  './agents.html',
  './concepts.html',
  './skill.html',
  './mcp.html',
  './news.html',
  './wiki-basics.html',
  './wiki-skills.html',
  './wiki-mcp.html',
  './comparison.html',
  './glossary.html',
  './manifest.json',
  './_shared/css/app.css',
  './_shared/css/splash.css',
  './_shared/js/app.js',
  './_shared/js/splash.js',
  './_shared/js/echarts.min.js',
  './assets/charts.js',
  './data/core-sources.json',
  './assets/icon-192.png',
  './assets/icon-192-maskable.png',
  './assets/icon-512.png',
  './assets/icon-512-maskable.png',
  './assets/ai-workbench.ico',
  './_shared/fonts/BricolageGrotesque-Regular.ttf',
  './_shared/fonts/BricolageGrotesque-Bold.ttf',
  './_shared/fonts/JetBrainsMono-Regular.ttf'
];

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

/* ---------- Activate：清理旧缓存 + 立即接管 ---------- */
self.addEventListener('activate', function (event) {
  event.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(
        keys.filter(function (key) {
          return key.indexOf('ai-wb-') === 0 && key.indexOf(CACHE_VERSION) !== 0;
        }).map(function (key) {
          return caches.delete(key);
        })
      );
    }).then(function () {
      return self.clients.claim();
    })
  );
});

/* ---------- Fetch：统一 Network First ---------- */
self.addEventListener('fetch', function (event) {
  var req = event.request;

  if (req.method !== 'GET') return;

  var url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  // 所有请求：Network First，离线回退缓存
  // 导航(HTML)请求强制绕过浏览器 HTTP 缓存，避免 GitHub Pages 的
  // max-age=600 导致更新后最多 10 分钟仍看到旧版（新闻延迟更新的根因）
  var fetchOpts = (req.mode === 'navigate') ? { cache: 'no-cache' } : undefined;
  var network = fetch(req, fetchOpts);
  // 在事件回调中登记异步写入；只有成功响应可以更新离线缓存。
  event.waitUntil(network.then(function (res) {
    if (!res.ok) return;
    var clone = res.clone();
    return caches.open(STATIC_CACHE).then(function (cache) {
      return cache.put(req, clone);
    });
  }).catch(function () {}));
  event.respondWith(
    network.then(function (res) {
      if (res.ok) return res;
      return caches.match(req).then(function (cached) { return cached || res; });
    }).catch(function () {
      return caches.match(req).then(function (cached) {
        if (cached) return cached;
        if (req.mode !== 'navigate') return Response.error();
        return caches.match('./index.html').then(function (home) {
          return home || new Response('当前离线，请联网后重试。', {
            status: 503, headers: { 'Content-Type': 'text/plain; charset=utf-8' }
          });
        });
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
