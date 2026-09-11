/* ============================================================
   移动端启动页控制器（Splash Screen）
   ------------------------------------------------------------
   只在「手机端」且「本会话尚未播放过」时展示一次。

   设计取舍（重要，改前先读）：
   1. 只认窄屏，不认「是否为 PWA 安装版」——安卓 Chrome 里
      网页版与安装版在系统启动图行为上不一致，用屏宽判断最稳。
   2. 每次「会话」只播一次（sessionStorage），不是每次跳页都播。
      否则站内切页会反复闪启动页，体验灾难。
   3. 提供 2.6s 兜底：即使动画事件没触发也一定收场，
      绝不把用户卡在启动页上。
   4. 点任意处 = 立即跳过。
   ============================================================ */
(function () {
  'use strict';

  var MOBILE_MAX = 640;          // 与 app.css 的移动端断点保持一致
  var HOLD_MS = 2350;            // 动画播完后的停留时长
  var SEEN_KEY = 'wb-splash-seen';

  function isMobile() {
    return window.matchMedia('(max-width: ' + MOBILE_MAX + 'px)').matches;
  }

  /* 尊重系统「减少动态效果」：直接不播，别折磨人 */
  function prefersReducedMotion() {
    try {
      return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    } catch (e) {
      return false;
    }
  }

  function alreadySeen() {
    try {
      return sessionStorage.getItem(SEEN_KEY) === '1';
    } catch (e) {
      /* 隐私模式下 sessionStorage 可能抛错 —— 按"已看过"处理，宁可不播 */
      return true;
    }
  }

  function markSeen() {
    try { sessionStorage.setItem(SEEN_KEY, '1'); } catch (e) { /* 忽略 */ }
  }

  function build() {
    var el = document.createElement('div');
    el.className = 'wb-splash';
    el.setAttribute('role', 'presentation');
    el.setAttribute('aria-hidden', 'true');
    el.innerHTML =
      '<div class="wb-splash__safe"></div>' +
      '<div class="wb-splash__grid"></div>' +
      '<div class="wb-splash__stars"></div>' +
      '<div class="wb-splash__scan"></div>' +
      '<div class="wb-splash__stage">' +
        '<div class="wb-splash__ring-a"></div>' +
        '<div class="wb-splash__glow"></div>' +
        '<div class="wb-splash__ring-b"></div>' +
        '<div class="wb-splash__badge"><span>AI</span></div>' +
      '</div>' +
      '<p class="wb-splash__title">AI 学习工作台</p>' +
      '<p class="wb-splash__sub">AI Learning Workbench</p>' +
      '<div class="wb-splash__bar"><i></i></div>' +
      '<div class="wb-splash__hint">轻触任意处跳过</div>';
    return el;
  }

  function run() {
    var el = build();
    var done = false;
    var timer = null;

    function finish() {
      if (done) return;
      done = true;
      if (timer) clearTimeout(timer);
      el.classList.add('is-out');
      /* 等淡出过渡结束再摘除节点，避免动画被截断 */
      setTimeout(function () {
        if (el.parentNode) el.parentNode.removeChild(el);
      }, 550);
    }

    el.addEventListener('click', finish);
    el.addEventListener('touchend', finish, { passive: true });

    document.body.appendChild(el);

    /* 下一帧再加类，确保过渡动画能从头播（否则会被合并掉） */
    requestAnimationFrame(function () {
      el.classList.add('is-on');
      markSeen();
      timer = setTimeout(finish, HOLD_MS);
    });
  }

  function boot() {
    if (!isMobile()) return;
    if (prefersReducedMotion()) return;
    if (alreadySeen()) return;
    run();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
