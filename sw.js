/* ============================================================
   AI 学习工作台 · Service Worker v4
   策略：所有资源 Network First，离线回退 Cache；
        导航(HTML)请求强制 no-cache，避免 GitHub Pages 缓存造成新闻延迟更新。
        版本升级会强制清除旧版残留缓存，根治“一直看旧内容”。
        v6：模型页改为五块知识分块（榜单/模型库/图表/价格/选型），
            charts.js 改为延迟初始化，务必清缓存。
        v7：模型页重构为两块（模型全景 / 规格与价格），删掉能力榜单、
            能力图表、选型指南；模型库改为图表驱动并支持点击下钻；
            价格表支持排序筛选。app.js 主题改为解析时立即应用。
   ============================================================ */

var CACHE_VERSION = 'ai-wb-v7';
var STATIC_CACHE = CACHE_VERSION + '-static';
var PAGE_CACHE = CACHE_VERSION + '-pages';

// 需要预缓存的资源
var PRECACHE_URLS = [
  './',
  './index.html',
  './models.html',
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
  event.respondWith(
    fetch(req, fetchOpts).then(function (res) {
      var clone = res.clone();
      caches.open(STATIC_CACHE).then(function (cache) {
        cache.put(req, clone);
      }).catch(function () {});
      return res;
    }).catch(function () {
      return caches.match(req).then(function (cached) {
        if (cached) return cached;
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
