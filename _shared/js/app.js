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
    // 如果 DOM 已就绪，立即显示 banner
    var banner = document.getElementById('install-banner');
    if (banner) {
      try { if (!localStorage.getItem('install-dismissed')) banner.style.display = 'flex'; } catch (err) {}
    }
    // 显示手动安装按钮
    var manualBtn = document.getElementById('manual-install-btn');
    if (manualBtn) manualBtn.style.display = 'flex';
  });

  /* ---------- 主题切换 ---------- */
  function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
  }
  function initTheme() {
    var saved = null;
    try { saved = localStorage.getItem('wb-theme'); } catch (e) {}
    var theme = saved || (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
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

  /* ---------- PWA Service Worker 注册 ---------- */
  function initServiceWorker() {
    if ('serviceWorker' in navigator) {
      window.addEventListener('load', function () {
        navigator.serviceWorker.register('./sw.js').then(function (reg) {
          reg.addEventListener('updatefound', function () {
            var newWorker = reg.installing;
            newWorker.addEventListener('statechange', function () {
              if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
                console.log('[PWA] 新版本已就绪，刷新页面更新');
              }
            });
          });
        }).catch(function (err) {
          console.warn('[PWA] Service Worker 注册失败:', err);
        });
      });
    }
  }

  /* ---------- 底部导航（移动端）---------- */
  function initBottomNav() {
    var pages = [
      { href: 'index.html',      icon: '🏠', label: '首页' },
      { href: 'models.html',     icon: '🤖', label: '模型' },
      { href: 'concepts.html',   icon: '📖', label: '百科' },
      { href: 'skill.html',      icon: '⚡', label: 'Skill' },
      { href: 'mcp.html',        icon: '🔌', label: 'MCP' }
    ];
    var current = location.pathname.split('/').pop() || 'index.html';
    var html = '<div class="bottom-nav-inner">';
    pages.forEach(function(p) {
      var active = p.href === current ? ' class="active"' : '';
      html += '<a href="' + p.href + '"' + active + '><span class="bn-icon">' + p.icon + '</span><span>' + p.label + '</span></a>';
    });
    html += '</div>';
    var nav = document.createElement('nav');
    nav.className = 'bottom-nav';
    nav.innerHTML = html;
    document.body.appendChild(nav);
  }

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
    // 已安装则跳过
    if (window.matchMedia('(display-mode: standalone)').matches) {
      var banner = document.getElementById('install-banner');
      if (banner) banner.style.display = 'none';
      return;
    }

    var banner = document.getElementById('install-banner');
    var manualBtn = document.getElementById('manual-install-btn');

    // 如果 beforeinstallprompt 已经触发（在 DOMContentLoaded 之前），显示 banner
    if (banner && deferredPrompt) {
      try {
        if (!localStorage.getItem('install-dismissed')) {
          banner.style.display = 'flex';
        }
      } catch (e) {}
    }

    // 如果已有 deferredPrompt，显示手动安装按钮
    if (manualBtn && deferredPrompt) {
      manualBtn.style.display = 'flex';
    }

    // 安装按钮点击
    function triggerInstall() {
      if (!deferredPrompt) {
        // 如果没有 beforeinstallprompt，提示用户手动安装
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
    initBottomNav();
    initGlossary();
    initTabs();
    initDates();
    initInstallPrompt();
  });
})();
