/* ============================================================
   AI 学习工作台 · 共享交互脚本
   ============================================================ */
(function () {
  'use strict';

  /* ---------- PWA: 立即捕获 beforeinstallprompt（不等 DOMContentLoaded） ---------- */
  var deferredPrompt = null;
  window.addEventListener('beforeinstallprompt', function (e) {
    e.preventDefault();
    deferredPrompt = e;
    var banner = document.getElementById('install-banner');
    if (banner) {
      try { if (!localStorage.getItem('install-dismissed')) banner.style.display = 'flex'; } catch (err) {}
    }
    var manualBtn = document.getElementById('manual-install-btn');
    if (manualBtn) manualBtn.style.display = 'flex';
  });

  /* ---------- 主题切换 ---------- */
  function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
  }
  function currentTheme() {
    var saved = null;
    try { saved = localStorage.getItem('wb-theme'); } catch (e) {}
    return saved ||
      (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
  }

  /* 关键：主题必须在本脚本被解析时就落到 <html data-theme> 上，不能等 DOMContentLoaded。
   * 否则页面内联脚本先跑（ECharts 按默认配色渲染），主题再被套上就得销毁重建一遍，
   * 表现为「图表闪一下换色」+ 多一次无谓渲染。 */
  applyTheme(currentTheme());

  function initTheme() {
    var theme = currentTheme();
    applyTheme(theme);
    var btn = document.querySelector('[data-theme-btn]');
    if (btn) {
      btn.textContent = theme === 'dark' ? '☀' : '☾';
      btn.addEventListener('click', function () {
        var next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
        applyTheme(next);
        btn.textContent = next === 'dark' ? '☀' : '☾';
        try { localStorage.setItem('wb-theme', next); } catch (e) {}
      });
    }
  }

  /* ---------- 词典搜索 ---------- */
  function initGlossary() {
    var input = document.querySelector('[data-gloss-search]');
    var items = Array.prototype.slice.call(document.querySelectorAll('[data-gloss-item]'));
    if (!input || !items.length) return;
    input.addEventListener('input', function () {
      var q = input.value.trim().toLowerCase();
      items.forEach(function (item) {
        var hay = (item.getAttribute('data-hay') || '').toLowerCase();
        var show = !q || hay.indexOf(q) !== -1;
        item.classList.toggle('hidden', !show);
      });
      var emptyEl = document.querySelector('[data-gloss-empty]');
      var visible = items.filter(function (it) { return !it.classList.contains('hidden'); }).length;
      if (emptyEl) emptyEl.classList.toggle('hidden', visible > 0);
    });
  }

  /* ---------- 动态区页签 ---------- */
  function initTabs() {
    var btns = Array.prototype.slice.call(document.querySelectorAll('[data-tab-btn]'));
    if (!btns.length) return;
    btns.forEach(function (btn) {
      btn.addEventListener('click', function () {
        var target = btn.getAttribute('data-tab-btn');
        btns.forEach(function (b) { b.classList.toggle('active', b === btn); });
        var panes = Array.prototype.slice.call(document.querySelectorAll('[data-tab-pane]'));
        panes.forEach(function (p) { p.classList.toggle('active', p.getAttribute('data-tab-pane') === target); });
      });
    });
  }

  /* ---------- PWA Service Worker 注册 + 自动更新 ---------- */
  function initServiceWorker() {
    if (!('serviceWorker' in navigator)) return;

    // 关键修复：新 SW 接管控制后，自动刷新一次页面，
    // 否则页面会一直停留在旧 SW 服务的缓存内容（新闻不更新的根因）。
    var reloading = false;
    navigator.serviceWorker.addEventListener('controllerchange', function () {
      if (reloading) return;
      reloading = true;
      window.location.reload();
    });

    window.addEventListener('load', function () {
      navigator.serviceWorker.register('./sw.js').then(function (reg) {
        // 若已有“等待中”的新 SW 且当前被旧 SW 控制，立刻催促其接管
        if (reg.waiting && navigator.serviceWorker.controller) {
          reg.waiting.postMessage('skipWaiting');
        }
        reg.addEventListener('updatefound', function () {
          var newWorker = reg.installing;
          if (!newWorker) return;
          newWorker.addEventListener('statechange', function () {
            // 新 SW 安装完成、且当前有旧控制器 → 催促其立即接管；
            // 接管成功后 controllerchange 触发上面的自动刷新
            if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
              newWorker.postMessage('skipWaiting');
              console.log('[PWA] 检测到新版本，即将自动刷新');
            }
          });
        });
      }).catch(function (err) {
        console.warn('[PWA] Service Worker 注册失败:', err);
      });
    });
  }

  /* ---------- 自动更新保险：切回前台 / 定时 检查更新 ---------- */
  function initAutoUpdate() {
    if (!('serviceWorker' in navigator)) return;

    var lastCheck = 0;
    var bannerShown = false;

    function showUpdateBanner() {
      if (bannerShown) return;
      bannerShown = true;
      var bar = document.createElement('div');
      bar.id = 'update-banner';
      bar.style.cssText = 'position:fixed;top:0;left:0;right:0;z-index:9999;' +
        'background:#2563eb;color:#fff;font-size:14px;text-align:center;' +
        'padding:10px 12px;display:flex;align-items:center;justify-content:center;gap:12px;' +
        'box-shadow:0 2px 8px rgba(0,0,0,.2)';
      bar.innerHTML = '<span>📰 有新的每日动态，</span>' +
        '<button id="update-now" style="background:#fff;color:#2563eb;border:0;border-radius:6px;' +
        'padding:4px 12px;font-weight:600;cursor:pointer;">立即刷新</button>' +
        '<button id="update-close" style="background:transparent;color:#fff;border:0;' +
        'font-size:18px;line-height:1;cursor:pointer;">×</button>';
      document.body.appendChild(bar);
      document.getElementById('update-now').addEventListener('click', function () {
        window.location.reload();
      });
      document.getElementById('update-close').addEventListener('click', function () {
        bar.remove();
        bannerShown = false;
      });
    }

    function checkForUpdates() {
      var now = Date.now();
      if (now - lastCheck < 30000) return; // 30s 内不重复检查
      lastCheck = now;

      // 1) 催促 SW 检查自身新版（waiting -> skipWaiting -> 接管自动刷新）
      if (navigator.serviceWorker.controller) {
        navigator.serviceWorker.getRegistration().then(function (reg) {
          if (!reg) return;
          reg.update();
          if (reg.waiting) reg.waiting.postMessage('skipWaiting');
        }).catch(function () {});
      }

      // 2) 内容新鲜度探针：仅新闻页。拉最新 news.html，对比首条日期
      var cur = document.querySelector('.ddate');
      if (!cur) return;
      fetch('news.html', { cache: 'no-store' }).then(function (res) {
        return res.text();
      }).then(function (html) {
        var m = html.match(/class="ddate">([^<]+)</);
        if (!m) return;
        var fresh = m[1].trim();
        var curTxt = cur.textContent.trim();
        // 首条日期更新（晚于当前展示）即认为有新版内容
        if (fresh && curTxt && fresh > curTxt) showUpdateBanner();
      }).catch(function () {});
    }

    // 切回前台（含从后台标签页切回）时检查一次
    document.addEventListener('visibilitychange', function () {
      if (!document.hidden) checkForUpdates();
    });

    // 定时兜底：每 15 分钟检查一次（覆盖长时间开着的标签页）
    setInterval(checkForUpdates, 15 * 60 * 1000);
  }

  /* ---------- 底部导航（移动端）· 立即创建 + 滚动兜底 ---------- */
  var bottomNavHtml = (function () {
    var pages = [
      { href: 'index.html',      icon: '🏠', label: '首页' },
      { href: 'models.html',     icon: '🧠', label: '模型' },
      { href: 'agents.html',     icon: '🤖', label: '智能体' },
      { href: 'concepts.html',   icon: '📖', label: '百科' }
    ];
    var current = location.pathname.split('/').pop() || 'index.html';
    var html = '<div class="bottom-nav-inner">';
    pages.forEach(function(p) {
      var active = p.href === current ? ' class="active"' : '';
      html += '<a href="' + p.href + '"' + active + '><span class="bn-icon">' + p.icon + '</span><span>' + p.label + '</span></a>';
    });
    html += '</div>';
    return html;
  })();

  function ensureBottomNav() {
    var existing = document.querySelector('.bottom-nav');
    if (!existing && document.body) {
      var nav = document.createElement('nav');
      nav.className = 'bottom-nav';
      nav.innerHTML = bottomNavHtml;
      document.body.appendChild(nav);
    }
  }

  // 立即创建（script 在 body 末尾，body 已存在）
  ensureBottomNav();

  // 滚动兜底：如果 nav 被浏览器丢弃，重新创建
  var scrollTimer = null;
  window.addEventListener('scroll', function () {
    if (scrollTimer) return;
    scrollTimer = setTimeout(function () {
      scrollTimer = null;
      ensureBottomNav();
    }, 200);
  }, { passive: true });

  // 页面完全加载后再确认一次
  window.addEventListener('load', ensureBottomNav);

  /* ---------- 日期 ---------- */
  function fmtDate(d) {
    var p = function (n) { return n < 10 ? '0' + n : '' + n; };
    return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate());
  }
  function initDates() {
    var el = document.querySelector('[data-today]');
    if (el) el.textContent = fmtDate(new Date());
    var wd = document.querySelector('[data-weekday]');
    if (wd) {
      var names = ['星期日', '星期一', '星期二', '星期三', '星期四', '星期五', '星期六'];
      wd.textContent = names[new Date().getDay()];
    }
  }

  /* ---------- PWA 安装引导 ---------- */
  function initInstallPrompt() {
    if (window.matchMedia('(display-mode: standalone)').matches) {
      var banner = document.getElementById('install-banner');
      if (banner) banner.style.display = 'none';
      return;
    }

    var banner = document.getElementById('install-banner');
    var manualBtn = document.getElementById('manual-install-btn');

    if (banner && deferredPrompt) {
      try {
        if (!localStorage.getItem('install-dismissed')) {
          banner.style.display = 'flex';
        }
      } catch (e) {}
    }

    if (manualBtn && deferredPrompt) {
      manualBtn.style.display = 'flex';
    }

    function triggerInstall() {
      if (!deferredPrompt) {
        alert('请点击浏览器右上角菜单 (⋮) → "添加到主屏幕" 来安装此应用');
        return;
      }
      deferredPrompt.prompt();
      deferredPrompt.userChoice.then(function () {
        deferredPrompt = null;
        if (banner) banner.style.display = 'none';
        if (manualBtn) manualBtn.style.display = 'none';
      });
    }

    var btn = document.getElementById('install-btn');
    if (btn) btn.addEventListener('click', triggerInstall);

    if (manualBtn) manualBtn.addEventListener('click', triggerInstall);

    var closeBtn = document.getElementById('install-close');
    if (closeBtn) {
      closeBtn.addEventListener('click', function () {
        if (banner) banner.style.display = 'none';
        try { localStorage.setItem('install-dismissed', '1'); } catch (e) {}
      });
    }

    window.addEventListener('appinstalled', function () {
      if (banner) banner.style.display = 'none';
      if (manualBtn) manualBtn.style.display = 'none';
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    initTheme();
    initServiceWorker();
    initAutoUpdate();
    initGlossary();
    initTabs();
    initDates();
    initInstallPrompt();
    ensureBottomNav(); // 再确认一次
    ChatBot.ensure();  // AI 对话悬浮球：再确认一次
  });

  /* ============================================================
     AI 对话悬浮球 · ChatBot
     全站由本脚本解析时向 body 注入（悬浮球 + 对话面板 + 设置），
     样式见 app.css 内 .ai-* 段。接 OpenAI 兼容接口，Key 仅存本浏览器。
     ============================================================ */
  var ChatBot = (function () {
    var LS_CFG = 'wb-ai-cfg';
    var LS_CHAT = 'wb-ai-chat';
    var MAX_HIST = 60;  // 会话历史上限（条，FIFO）
    var MAX_SEND = 20;  // 每次请求携带的最近历史条数
    var EP = '/chat/completions';

    var PRESETS = [
      { id: 'deepseek', name: 'DeepSeek',      base: 'https://api.deepseek.com/v1',                        model: 'deepseek-chat' },
      { id: 'kimi',     name: 'Kimi (Moonshot)', base: 'https://api.moonshot.cn/v1',                       model: 'moonshot-v1-8k' },
      { id: 'zhipu',    name: '智谱 GLM',       base: 'https://open.bigmodel.cn/api/paas/v4',               model: 'glm-4-flash' },
      { id: 'qwen',     name: '通义千问',       base: 'https://dashscope.aliyuncs.com/compatible-mode/v1',  model: 'qwen-plus' },
      { id: 'custom',   name: '自定义',         base: '',                                                    model: '' }
    ];

    var SYSTEM_PROMPT =
      '你是「AI 学习工作台」的站内助手。本站是一个中文 AI 学习资料站，' +
      '持续收录国内外大模型、智能体应用、Agent Skills、MCP 工具与 AI 基础概念，内容每日更新。' +
      '回答要求：1) 优先基于本站已收录的模型 / 智能体 / 概念作答，可建议用户去 models、agents、concepts、wiki 等页面细看；' +
      '2) 用中文回答，尽量结构化（分点、小标题）；' +
      '3) 涉及数据（参数、价格、榜单、日期）时标注信息口径与时间点，不确定就说明不确定，绝不编造具体数字；' +
      '4) 代码示例用 markdown 代码块包裹。';

    var cfg = null;
    var root = null, fab = null, panel = null;
    var chatView = null, msgsEl = null, composerEl = null, inputEl = null, sendBtn = null, metaEl = null;
    var setupView = null;
    var streaming = false, controller = null;
    var curAcc = ''; // 流式当前累计文本

    /* ---------- 工具 ---------- */
    function safeGet(k) {
      try { return localStorage.getItem(k); } catch (e) { return null; }
    }
    function safeSet(k, v) {
      try { localStorage.setItem(k, v); } catch (e) {}
    }
    function safeDel(k) {
      try { localStorage.removeItem(k); } catch (e) {}
    }
    function loadCfg() {
      var raw = safeGet(LS_CFG);
      if (raw) {
        try {
          cfg = JSON.parse(raw);
          if (cfg && typeof cfg === 'object' && cfg.base && cfg.model) return cfg;
        } catch (e) {}
      }
      cfg = { provider: 'deepseek', base: PRESETS[0].base, model: PRESETS[0].model, key: '' };
      return cfg;
    }
    function saveCfg() {
      safeSet(LS_CFG, JSON.stringify(cfg));
    }
    function loadHist() {
      var raw = safeGet(LS_CHAT);
      if (raw) {
        try {
          var arr = JSON.parse(raw);
          if (Object.prototype.toString.call(arr) === '[object Array]') return arr;
        } catch (e) {}
      }
      return [];
    }
    function saveHist(h) {
      var keep = h.slice(-MAX_HIST);
      safeSet(LS_CHAT, JSON.stringify(keep));
      return keep;
    }
    function escapeHtml(s) {
      return String(s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }
    function nl2br(s) { return s.replace(/\n/g, '<br>'); }
    function renderMarkdown(src) {
      // 先整体转义 → 摘出代码块 → 行内 code / 粗体 / URL / 换行 → 还原代码块
      var html = escapeHtml(src);
      var blocks = [];
      html = html.replace(/```(?:[a-zA-Z0-9_+-]*)\n?([\s\S]*?)```/g, function (_, code) {
        blocks.push(code);
        return '\u0000AI_CODE' + (blocks.length - 1) + '\u0000';
      });
      html = html.replace(/`([^`\n]+)`/g, '<code class="ai-ic">$1</code>');
      html = html.replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>');
      html = html.replace(/(https?:\/\/[^\s<\u0000]+)/g,
        '<a href="$1" target="_blank" rel="noopener noreferrer">$1</a>');
      html = nl2br(html);
      html = html.replace(/\u0000AI_CODE(\d+)\u0000/g, function (_, i) {
        return '<pre class="ai-code"><code>' + blocks[+i] + '</code></pre>';
      });
      return html;
    }

    /* ---------- DOM 构建 ---------- */
    function buildDOM() {
      root = document.createElement('div');
      root.id = 'ai-chat';

      // 悬浮球
      fab = document.createElement('button');
      fab.type = 'button';
      fab.className = 'ai-fab';
      fab.setAttribute('aria-label', '打开 AI 对话');
      fab.title = 'AI 助手';
      fab.innerHTML = '<span class="ai-fab-spark">✦</span>';
      root.appendChild(fab);

      // 面板
      panel = document.createElement('div');
      panel.className = 'ai-panel';
      panel.setAttribute('role', 'dialog');
      panel.setAttribute('aria-hidden', 'true');

      // 面板头
      var phead = document.createElement('div');
      phead.className = 'ai-phead';
      phead.innerHTML =
        '<div class="ai-ptitle"><span class="ai-plogo">✦</span><span>AI 助手</span>' +
        '<span class="ai-psub">OpenAI 兼容 · 本站增强</span></div>' +
        '<div class="ai-pbtns">' +
        '<button type="button" class="ai-icon" data-ai-setup title="设置" aria-label="设置">⚙</button>' +
        '<button type="button" class="ai-icon" data-ai-close title="收起" aria-label="收起">✕</button>' +
        '</div>';
      panel.appendChild(phead);

      // 聊天视图
      chatView = document.createElement('div');
      chatView.className = 'ai-chatview';

      msgsEl = document.createElement('div');
      msgsEl.className = 'ai-msgs';
      chatView.appendChild(msgsEl);

      composerEl = document.createElement('form');
      composerEl.className = 'ai-composer';
      composerEl.innerHTML =
        '<textarea class="ai-input" data-ai-input rows="1" placeholder="输入问题…  Enter 发送 / Shift+Enter 换行"></textarea>' +
        '<button type="submit" class="ai-send" data-ai-send>发送</button>';
      chatView.appendChild(composerEl);

      metaEl = document.createElement('div');
      metaEl.className = 'ai-meta';
      metaEl.textContent = '会话仅存于本浏览器 · 设置里填入你的 API Key';
      chatView.appendChild(metaEl);

      panel.appendChild(chatView);

      // 设置视图
      setupView = document.createElement('div');
      setupView.className = 'ai-setup';
      var optHtml = '';
      for (var i = 0; i < PRESETS.length; i++) {
        optHtml += '<option value="' + PRESETS[i].id + '">' + PRESETS[i].name + '</option>';
      }
      setupView.innerHTML =
        '<div class="ai-setup-head">' +
        '<button type="button" class="ai-back" data-ai-back title="返回对话">←</button>' +
        '<span>对话设置</span></div>' +
        '<label class="ai-fld">服务商' +
        '<select class="ai-sel" data-ai-provider>' + optHtml + '</select></label>' +
        '<label class="ai-fld">接口地址 Base URL' +
        '<input class="ai-inp" data-ai-base type="text" spellcheck="false" placeholder="https://api.deepseek.com/v1"></label>' +
        '<label class="ai-fld">模型' +
        '<input class="ai-inp" data-ai-model type="text" spellcheck="false" placeholder="deepseek-chat"></label>' +
        '<label class="ai-fld">API Key' +
        '<span class="ai-keyrow"><input class="ai-inp ai-key" data-ai-key type="password" ' +
        'placeholder="sk-…" autocomplete="off" spellcheck="false">' +
        '<button type="button" class="ai-keyeye" data-ai-keyeye title="显示 / 隐藏">👁</button></span></label>' +
        '<div class="ai-seta">' +
        '<button type="button" class="ai-btn" data-ai-test>测试连接</button>' +
        '<button type="button" class="ai-btn ai-solid" data-ai-save>保存</button>' +
        '</div>' +
        '<div class="ai-testmsg" data-ai-testmsg></div>' +
        '<div class="ai-seta ai-seta2">' +
        '<button type="button" class="ai-btn ai-clear" data-ai-clear>清空会话</button>' +
        '</div>' +
        '<p class="ai-secnote">🔒 API Key 仅存本浏览器 localStorage，不会上传本站服务器。<br>' +
        '请勿把页面分享给他人；个人学习自用，谨防 Key 泄露与盗刷。</p>';
      panel.appendChild(setupView);

      root.appendChild(panel);
      document.body.appendChild(root);
    }

    /* ---------- 面板开关 ---------- */
    function openPanel() {
      if (!root) return;
      panel.classList.add('open');
      panel.setAttribute('aria-hidden', 'false');
      fab.classList.add('hide');
      renderHistory();
      showChat();
      // 外部点击关闭
      setTimeout(function () {
        document.addEventListener('click', onDocClick);
      }, 0);
      focusInput();
    }
    function closePanel() {
      if (!panel) return;
      panel.classList.remove('open');
      panel.setAttribute('aria-hidden', 'true');
      fab.classList.remove('hide');
      document.removeEventListener('click', onDocClick);
    }
    function onDocClick(e) {
      if (!root.contains(e.target)) closePanel();
    }
    function focusInput() {
      if (inputEl && chatView && !chatView.classList.contains('hidden')) {
        try { inputEl.focus(); } catch (e) {}
      }
    }

    /* ---------- 聊天 / 设置视图切换 ---------- */
    function showChat() {
      chatView.classList.remove('hidden');
      setupView.classList.add('hidden');
    }
    function showSetup() {
      chatView.classList.add('hidden');
      setupView.classList.remove('hidden');
      fillSetupForm();
    }

    /* ---------- 消息渲染 ---------- */
    function renderHistory() {
      msgsEl.innerHTML = '';
      var h = loadHist();
      if (!h.length) {
        showWelcome();
        return;
      }
      for (var i = 0; i < h.length; i++) {
        if (h[i].role === 'user' || h[i].role === 'assistant') {
          appendMsgEl(h[i].role === 'user' ? 'user' : 'bot', h[i].content);
        }
      }
      scrollBottom();
    }
    function showWelcome() {
      msgsEl.innerHTML =
        '<div class="ai-welcome">' +
        '<div class="ai-w-ic">✦</div>' +
        '<p><b>你好，我是这个工作台的 AI 助手。</b></p>' +
        '<p>可以问我模型、智能体、Agent Skills、MCP 与 AI 概念相关的问题，' +
        '也可以直接写代码、做问答。回答会参考本站内容并建议你去对应页面细看。</p>' +
        '<p class="ai-w-hint">开始前先点右上角 ⚙ 填入你的大模型 API Key。</p></div>';
    }
    function appendMsgEl(kind, content) {
      var empty = msgsEl.querySelector('.ai-welcome');
      if (empty) empty.remove();
      var wrap = document.createElement('div');
      wrap.className = 'ai-msg ai-' + kind;
      if (kind === 'user') {
        var b = document.createElement('div');
        b.className = 'ai-bubble';
        b.textContent = content;
        wrap.appendChild(b);
      } else {
        var bc = document.createElement('div');
        bc.className = 'ai-bubble';
        bc.innerHTML = renderMarkdown(content);
        wrap.appendChild(bc);
        var meta = document.createElement('div');
        meta.className = 'ai-msgmeta';
        meta.textContent = 'AI';
        wrap.appendChild(meta);
      }
      msgsEl.appendChild(wrap);
      return wrap;
    }
    function appendError(text) {
      var e = document.createElement('div');
      e.className = 'ai-msg ai-error';
      e.innerHTML = '⚠ ' + escapeHtml(text);
      msgsEl.appendChild(e);
      scrollBottom();
    }
    function scrollBottom() {
      if (msgsEl) msgsEl.scrollTop = msgsEl.scrollHeight;
    }
    function setMeta(t) {
      if (metaEl) metaEl.textContent = t;
    }

    /* ---------- 设置面板 ---------- */
    function fillSetupForm() {
      loadCfg();
      var sel = setupView.querySelector('[data-ai-provider]');
      var base = setupView.querySelector('[data-ai-base]');
      var model = setupView.querySelector('[data-ai-model]');
      var key = setupView.querySelector('[data-ai-key]');
      var useCustom = true;
      for (var i = 0; i < PRESETS.length; i++) {
        if (PRESETS[i].id === cfg.provider && PRESETS[i].base === cfg.base) {
          sel.value = cfg.provider; useCustom = false; break;
        }
      }
      if (useCustom) sel.value = 'custom';
      base.value = cfg.base || '';
      model.value = cfg.model || '';
      key.value = cfg.key || '';
      clearTestMsg();
    }
    function onProviderChange() {
      var sel = setupView.querySelector('[data-ai-provider]');
      var base = setupView.querySelector('[data-ai-base]');
      var model = setupView.querySelector('[data-ai-model]');
      var p = null;
      for (var i = 0; i < PRESETS.length; i++) {
        if (PRESETS[i].id === sel.value) { p = PRESETS[i]; break; }
      }
      if (p && p.id !== 'custom') {
        base.value = p.base;
        model.value = p.model;
      }
      clearTestMsg();
    }
    function collectForm() {
      var sel = setupView.querySelector('[data-ai-provider]');
      var base = setupView.querySelector('[data-ai-base]');
      var model = setupView.querySelector('[data-ai-model]');
      var key = setupView.querySelector('[data-ai-key]');
      return {
        provider: sel.value,
        base: base.value.trim().replace(/\/+$/, ''),
        model: model.value.trim(),
        key: key.value.trim()
      };
    }
    function clearTestMsg() {
      var el = setupView.querySelector('[data-ai-testmsg]');
      if (el) { el.textContent = ''; el.className = 'ai-testmsg'; }
    }
    function setTestMsg(text, cls) {
      var el = setupView.querySelector('[data-ai-testmsg]');
      if (el) {
        el.textContent = text;
        el.className = 'ai-testmsg' + (cls ? ' ' + cls : '');
      }
    }
    function onSave() {
      var f = collectForm();
      if (!f.base) { setTestMsg('请填写接口地址 Base URL', 'fail'); return; }
      if (!f.model) { setTestMsg('请填写模型名', 'fail'); return; }
      if (!f.key) { setTestMsg('API Key 为空：可以保存，但发消息前需要填 Key', 'warn'); }
      cfg = { provider: f.provider, base: f.base, model: f.model, key: f.key };
      saveCfg();
      showChat();
      setMeta('已保存「' + (f.model) + '」配置');
      focusInput();
    }
    function onTest() {
      var f = collectForm();
      if (!f.base || !f.model) { setTestMsg('请先填写接口地址与模型名', 'fail'); return; }
      if (!f.key) { setTestMsg('请先填写 API Key', 'fail'); return; }
      setTestMsg('连接测试中…', 'pending');
      var ac = new AbortController();
      var timer = setTimeout(function () { ac.abort(); }, 20000);
      fetch(f.base + EP, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer ' + f.key
        },
        body: JSON.stringify({
          model: f.model,
          messages: [{ role: 'user', content: 'ping' }],
          max_tokens: 1,
          stream: false
        }),
        signal: ac.signal
      }).then(function (res) {
        clearTimeout(timer);
        if (res.ok) {
          setTestMsg('✔ 连接成功，Key 与配置可用', 'ok');
        } else {
          return res.text().then(function (txt) {
            setTestMsg('连接失败（HTTP ' + res.status + '）：' + shortErr(txt), 'fail');
          });
        }
      }).catch(function (err) {
        clearTimeout(timer);
        if (err && err.name === 'AbortError') setTestMsg('测试超时：检查网络或接口地址', 'fail');
        else setTestMsg('无法连接：' + netErrText(err), 'fail');
      });
    }
    function shortErr(body) {
      try {
        var j = JSON.parse(body);
        if (j && j.error) {
          var m = j.error.message || j.error.code || '';
          return typeof m === 'string' ? m.slice(0, 120) : '请求被拒绝';
        }
      } catch (e) {}
      return body ? String(body).slice(0, 120) : '未知错误';
    }
    function netErrText(err) {
      if (!err) return '未知错误';
      return '网络 / 跨域失败。请确认：接口地址为 HTTPS、服务端允许浏览器跨域（CORS），' +
        '且页面通过 http(s) 访问（直接双击 file:// 打开通常不行）。';
    }

    /* ---------- 发送与流式 ---------- */
    function onComposerSubmit(e) {
      e.preventDefault();
      if (streaming) { stopStream(); return; }
      var text = inputEl.value.replace(/\s+$/, '').trim();
      if (!text) return;
      var c = loadCfg();
      if (!c.key) {
        openPanel();
        showSetup();
        setTestMsg('还没有 API Key —— 选服务商、填 Key 后点「保存」', 'warn');
        return;
      }
      inputEl.value = '';
      autoGrow();
      appendMsgEl('user', text);
      scrollBottom();
      sendToApi(c, text);
    }
    function buildMessages(text) {
      var h = loadHist();
      var msgs = [];
      for (var i = 0; i < h.length; i++) {
        if (h[i].role === 'user' || h[i].role === 'assistant') {
          msgs.push({ role: h[i].role === 'user' ? 'user' : 'assistant', content: h[i].content });
        }
      }
      msgs = msgs.slice(-MAX_SEND);
      msgs.push({ role: 'user', content: text });
      return msgs;
    }
    function sendToApi(c, text) {
      setMeta('正在生成…（点「停止」可中断）');
      sendBtn.textContent = '停止';
      streaming = true;
      controller = new AbortController();
      var botWrap = appendMsgEl('bot', '');
      var bubble = botWrap.querySelector('.ai-bubble');
      curAcc = '';
      setBubble(bubble);

      var payload = {
        model: c.model,
        messages: [{ role: 'system', content: SYSTEM_PROMPT }].concat(buildMessages(text)),
        stream: true,
        temperature: 0.6
      };

      fetch(c.base + EP, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + c.key },
        body: JSON.stringify(payload),
        signal: controller.signal
      }).then(function (res) {
        if (!res.ok) {
          return res.text().then(function (txt) {
            throw httpError(res.status, txt);
          });
        }
        if (res.body && res.body.getReader) return readStream(res, bubble, botWrap, text);
        // 不支持流式 → 降级非流式
        return res.json().then(function (j) {
          var content = '';
          if (j && j.choices && j.choices[0]) content = j.choices[0].message && j.choices[0].message.content || '';
          finishBot(bubble, botWrap, content, text);
        });
      }).catch(function (err) {
        if (err && err.name === 'AbortError') {
          // 用户手动停止：保留已生成部分
          if (curAcc) {
            finishBot(bubble, botWrap, curAcc, text);
            setMeta('已停止');
          } else {
            botWrap.remove();
            setMeta('已停止');
          }
          return;
        }
        botWrap.remove();
        if (err && err.aiStatus) appendError(err.message);
        else appendError(netErrText(err));
        setMeta('会话仅存于本浏览器 · 设置里填入你的 API Key');
      }).finally(function () {
        streaming = false;
        controller = null;
        sendBtn.textContent = '发送';
      });
    }
    function httpError(status, txt) {
      var msg;
      if (status === 401) msg = 'API Key 无效或已过期（HTTP 401），请到 ⚙ 设置里核对';
      else if (status === 402 || status === 403) msg = '该 Key 欠费或无权限（HTTP ' + status + '）';
      else if (status === 429) msg = '请求过于频繁或额度不足（HTTP 429），稍后再试';
      else if (status >= 500) msg = '模型服务端错误（HTTP ' + status + '），稍后再试';
      else msg = '请求失败（HTTP ' + status + '）：' + shortErr(txt);
      var err = new Error(msg);
      err.aiStatus = true;
      return err;
    }
    function readStream(res, bubble, botWrap, text) {
      var reader = res.body.getReader();
      var decoder = new TextDecoder('utf-8');
      var acc = '';
      function pump() {
        return reader.read().then(function (r) {
          if (r.done) {
            flushLine();
            finishBot(bubble, botWrap, curAcc, text);
            return;
          }
          acc += decoder.decode(r.value, { stream: true });
          var lines = acc.split('\n');
          acc = lines.pop();
          for (var i = 0; i < lines.length; i++) handleLine(lines[i], bubble);
          return pump();
        });
      }
      function flushLine() {
        if (acc && acc.indexOf('data:') === 0) handleLine(acc, bubble);
      }
      return pump();
    }
    function handleLine(line, bubble) {
      var s = line.trim();
      if (s.indexOf('data:') !== 0) return;
      var data = s.slice(5).trim();
      if (!data || data === '[DONE]') return;
      try {
        var j = JSON.parse(data);
        if (j.choices && j.choices[0]) {
          var delta = j.choices[0].delta;
          var piece = delta && delta.content;
          if (piece) { curAcc += piece; setBubble(bubble); }
        }
      } catch (e) {}
    }
    function setBubble(bubble) {
      if (!bubble) return;
      bubble.innerHTML = curAcc ? renderMarkdown(curAcc) : '<span class="ai-thinking">…</span>';
      scrollBottom();
    }
    function finishBot(bubble, botWrap, content, text) {
      if (content) {
        var h = loadHist();
        h.push({ role: 'user', content: text });
        h.push({ role: 'assistant', content: content });
        saveHist(h);
      }
      if (bubble) bubble.innerHTML = content ? renderMarkdown(content) : '（无回复内容）';
      setMeta('会话仅存于本浏览器 · 设置里填入你的 API Key');
      scrollBottom();
    }
    function stopStream() {
      if (controller) controller.abort();
    }
    function autoGrow() {
      inputEl.style.height = 'auto';
      inputEl.style.height = Math.min(inputEl.scrollHeight, 140) + 'px';
    }
    function clearHistory() {
      safeDel(LS_CHAT);
      msgsEl.innerHTML = '';
      showWelcome();
      setMeta('会话已清空');
    }

    /* ---------- 事件绑定 ---------- */
    function bindEvents() {
      fab.addEventListener('click', function () {
        if (panel.classList.contains('open')) closePanel();
        else openPanel();
      });
      panel.addEventListener('click', function (e) {
        var t = e.target;
        var closer = t.closest ? t.closest('[data-ai-close]') : null;
        var setup = t.closest ? t.closest('[data-ai-setup]') : null;
        var back = t.closest ? t.closest('[data-ai-back]') : null;
        var save = t.closest ? t.closest('[data-ai-save]') : null;
        var test = t.closest ? t.closest('[data-ai-test]') : null;
        var clear = t.closest ? t.closest('[data-ai-clear]') : null;
        var eye = t.closest ? t.closest('[data-ai-keyeye]') : null;
        if (closer) { e.stopPropagation(); closePanel(); return; }
        if (setup) { e.stopPropagation(); showSetup(); return; }
        if (back) { e.stopPropagation(); showChat(); focusInput(); return; }
        if (save) { e.stopPropagation(); onSave(); return; }
        if (test) { e.stopPropagation(); onTest(); return; }
        if (clear) { e.stopPropagation(); clearHistory(); return; }
        if (eye) {
          e.stopPropagation();
          var k = setupView.querySelector('[data-ai-key]');
          if (k.type === 'password') { k.type = 'text'; eye.textContent = '🙈'; }
          else { k.type = 'password'; eye.textContent = '👁'; }
          return;
        }
      });
      var provSel = setupView.querySelector('[data-ai-provider]');
      if (provSel) provSel.addEventListener('change', onProviderChange);
      inputEl.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          if (composerEl.requestSubmit) composerEl.requestSubmit();
          else onComposerSubmit({ preventDefault: function () {} });
        }
      });
      inputEl.addEventListener('input', autoGrow);
      composerEl.addEventListener('submit', onComposerSubmit);
    }

    /* ---------- 初始化 ---------- */
    function ensure() {
      if (root && document.body.contains(root)) return;
      if (!document.body) return;
      loadCfg();
      buildDOM();
      // 先取元素引用，再绑事件（bindEvents 内部依赖这些引用）
      sendBtn = panel.querySelector('[data-ai-send]');
      inputEl = panel.querySelector('[data-ai-input]');
      msgsEl = panel.querySelector('.ai-msgs');
      metaEl = panel.querySelector('.ai-meta');
      chatView = panel.querySelector('.ai-chatview');
      setupView = panel.querySelector('.ai-setup');
      bindEvents();
      renderHistory();
    }

    return { ensure: ensure };
  })();

  // 立即构建（script 位于 body 末尾，body 已存在；与 ensureBottomNav 同策略）
  ChatBot.ensure();
})();
