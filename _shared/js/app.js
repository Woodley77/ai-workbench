/* ============================================================
   AI 学习工作台 · 共享交互脚本
   ============================================================ */
(function () {
  'use strict';

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

  /* ---------- PWA manifest ---------- */
  function initManifest() {
    var link = document.createElement('link');
    link.rel = 'manifest';
    link.href = './manifest.json';
    document.head.appendChild(link);
  }

  /* ---------- 底部导航（移动端）---------- */
  function initBottomNav() {
    var pages = [
      { href: 'index.html',      icon: '🏠', label: '首页' },
      { href: 'models.html',     icon: '🤖', label: '模型' },
      { href: 'concepts.html',   icon: '📖', label: '概念' },
      { href: 'comparison.html', icon: '📊', label: '对比' },
      { href: 'glossary.html',   icon: '📚', label: '词典' },
      { href: 'news.html',       icon: '📰', label: '动态' }
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

  document.addEventListener('DOMContentLoaded', function () {
    initTheme();
    initManifest();
    initBottomNav();
    initGlossary();
    initTabs();
    initDates();
  });
})();
