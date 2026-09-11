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
        v13：新增「智能体应用」页（agents.html）——25 个国内外 Agent 应用图鉴、
             7 组热度榜、4 张图表、场景选型卡与国内外差异；顶部导航由 4 项增至
             5 页签、移动端底部导航由 3 项增至 4 项；务必清缓存。
        v14：agents.html 完善 —— 国内应用 14 → 24（新增讯飞星火 / WPS 灵犀 /
             TRAE / 秘塔 / 飞书 / 纳米 / 天工 / FastGPT / ima / RagFlow），
             国外 11 条改收进「海外速览」紧凑区以突出国内主体；图鉴新增搜索框与
             三种排序；修 cnmau 榜因单位混用导致的条形失真；页脚补来源清单；
             update_content.py 新增 AGENT 分支，动态区开始真正每日自动追加。
        v15：全站接入 AI 对话悬浮球（ChatBot）—— 对话面板由 app.js 动态注入、
             样式进 app.css（无新增静态文件）；背景视觉高级化（细网格 + 噪点 +
             暗角 + 玻璃卡片高光发丝线），明暗双主题同步升级；务必清缓存。
        v16：内容新鲜度探针从仅 news 页推广到全部动态页（首页/新闻/agents/
             wiki-skills/wiki-mcp）—— 每 15 分钟 + 切回前台静默比对最大日期，
             有更新弹「✨ 有新内容」刷新条；修复长开页面看不到每日更新的问题。
        v17：动态区重构——news.html「每日动态」由一天一坨时间线改为四个主题模块
             （智能体/大模型/技能与MCP/综合要闻），各模块每日 08:23/18:23 独立
             追加、模块级防重；历史 Google 链接旧块整块清除；agents.html 的
             「Agent 赛道每日更新」并入动态区「智能体动态」模块；国外区保留。
        v18：动态区其余三 tab（新模型速报/行业大事记/论文快报）动态化——
             各加 __RELEASE__/__MILESTONE__/__PAPERS__ marker 每日自动追加
             （有命中才更新），置顶「2026-09」精编块（补 OpenAI GPT-6 Astra /
             ChatGPT Images 2.5 / DeepSeek V4.1 Flash 预告 等窗口外内容）。
        v19：每日动态取消四主题模块，只按国内外分两块——
             🇨🇳 国内动态(__DOMESTIC_INSERT__) / 🌍 国外动态(__FOREIGN_INSERT__)，
             历史分模块内容清空重来；块内不再重复国内外标签（模块本身即单边）。
        v20：模型页定位散点图改按厂商分组分色（原按 cat 分组，过滤后阵营坍缩成
             单值 → 图例仅 1 项、所有点同色）；图表移动端适配（热力图改横向滚动
             而非压缩坐标系）与科技风美化；新增 --chart-c1..c12 配色 token。
        v21：移动端启动页（深空墨绿 + 电弧光环 + 星轨粒子 + 扫描线 + 进度条）——
             新增 _shared/css/splash.css 与 _shared/js/splash.js，8 个页面各注入
             一次引用；仅 <=640px 触发、每会话只播一次、可点击跳过、尊重系统
             「减少动态效果」；manifest 底色由近白 #F4FBF7 改深空 #0A1512，
             消除系统启动帧的白闪。务必清缓存。
        v22：应用图标整组重做（深色科技风）—— 深空底 + 细网格 + 虚线外环 +
             亮绿电弧环 + 玻璃徽标 + 发光 AI，与启动页同一视觉语言；maskable
             与 any 拆成独立文件（新增 icon-192/512-maskable.png，徽标缩小以落在
             中心 80% 安全区内）；8 页 <meta theme-color> 由绿改深空、apple-touch-icon
             由 ico 改 icon-192.png；favicon(ico) 同步重做。务必清缓存。
        v23：能力热力图改造为「左列固定 + 右侧横向滚动」——
             原图整体横滑时左边模型名会跟着跑掉、认不出哪行是哪家。
             现在把 Y 轴标签搬到独立的左列（自绘 DOM），只有右侧格子区滚动；
             两列行高由 ECharts 实测反推后写入内联样式，保证像素级对齐。
             改动的资源：models.html + assets/charts.js（共享） +
             _shared/css/app.css（窄屏规则共用），务必清缓存。
        v24：修 v23 的三个线上问题（用户反馈「效果不行而且会卡」）——
             ① 删掉错误的滚动同步：左列是 .heat-scroll 的**兄弟节点**，
                本来就不在滚动容器里、天然静止，却给它加了
                translateX(scrollLeft)，滑动时模型名反而往右跑出左列被裁掉。
                连带删掉 document 上的捕获阶段 scroll 监听。
             ② 画布太矮：min-height 330 → 420；HEAT_TOP 74 → 56、
                HEAT_BOTTOM 16 → 28（给色阶图例留位）。
                行高从 24px 提到 33.6px（文字两行需 27px，原先放不下）。
                新增行高下限保护：不够高时自动撑高画布，模型变多也不挤。
             ③ 卡顿：移除 .heat-scroll 的 inset box-shadow（画在内容之上、
                滚动每帧重绘），改静态 border；transform 同步已删除。
                另修 visualMap 配置写反（horizontal 却给 12×110，渲染成竖带）
                → 改 132×9。务必清缓存。
        v25：禁止页面双指缩放——用户反馈模型页「整个页面可以缩放了，缩放的特别
             不稳定，把下面几大块内容都埋没了」。8 个页面 viewport meta
             maximum-scale 5.0 -> 1.0 + user-scalable=no；app.js 注入 iOS Safari
             兜底（gesturestart preventDefault + 多指 touchmove 阻止，passive:false）。
             背景：图表区需要频繁单指横滑，极易误触捏合；页面被放大后下方内容
             全部推出屏幕。站内无任何多指手势需求，阻止无副作用。务必清缓存。
        v26：修电脑端热力图中央「大竖杠」—— v24 修 visualMap 时把
             itemWidth/itemHeight 语义又搞反了（注释断言「horizontal 时
             itemWidth 是长度」是错的）。ECharts 真实语义【不随 orient 交换】：
             itemWidth=厚度(竖直)、itemHeight=长度(水平)，内部先按此画矩形
             再旋转 90°（SVG 实测 transform matrix(0,-1,1,0,…)）。
             132×9 实际渲染成 9宽×132高 的竖杠杵在图中央（强弱文字挤成一团）。
             修复：itemWidth:9 + itemHeight:132 → 132宽×9高 横条；
             bottom 4→6、HEAT_BOTTOM 28→38 给横条+文字留位（行高 33.6→32.6，
             仍高于 32 下限）。SVG 渲染实测：横条后强弱文字间距 152px（坏配置 29px）。
             改动的资源：assets/charts.js，务必清缓存。
   ============================================================ */

var CACHE_VERSION = 'ai-wb-v26';
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
