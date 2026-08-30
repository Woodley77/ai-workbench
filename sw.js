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
        v8：模型页只保留国产模型做展示与比较——国外模型全部移出图表、
            规格与价格，仅保留在「全部模型」表中；SWE-bench 实测节删除。
        v9：全部模型表改为国产在前、海外在后；热力图/定位散点图只留 10 个
            国产主力大模型；散点图修掉点与标签重叠（轴按数据收窄 + 自动错开）。
        v10：模型页与百科新增「最新动态」区块（models / wiki-skills / wiki-mcp），
             由 scripts/update_content.py 每日自动追加；三页加了插入标记，务必清缓存。
        v11：散点图标签改用细引线(callout)指向圆点、拥挤处自动避让且不隐藏；
             模型页新增三块高价值模块（场景选型卡 / 国产平替映射 / 性价比红黑榜）。
        v12：模型页移除「最新动态」新闻区（news 内容只留在 news.html 与百科页），
             模型页不再参与每日新闻更新；务必清缓存。
   ============================================================ */

var CACHE_VERSION = 'ai-wb-v12';
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
