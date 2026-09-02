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
  });
})();
