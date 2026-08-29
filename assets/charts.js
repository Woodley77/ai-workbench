/* 模型对比页 · 图表脚本
 * 设计要点：图表只注册「构造 option 的函数」，不立即 echarts.init。
 * 因为图表可能位于隐藏的标签页内（display:none → 尺寸为 0），
 * 立即初始化会得到 0×0 的画布；改为切到该页时再 ensure() 初始化。
 * 对外暴露 window.WB_CHARTS：
 *   .builders   { elId: function(): option }
 *   .ensure(id) 初始化（不可见则跳过）并返回实例
 *   .ensureVisible()  初始化当前所有可见的图表
 *   .resizeVisible()  对已初始化且可见的图表 resize
 *   .rebuildAll()     主题切换后销毁重建，保证配色跟随 CSS 变量
 */
(function () {
  'use strict';

  var builders = {};
  var instances = {};

  function readVars() {
    var s = getComputedStyle(document.documentElement);
    return {
      accent:  s.getPropertyValue('--accent').trim(),
      accent2: s.getPropertyValue('--accent2').trim(),
      ink:     s.getPropertyValue('--ink').trim(),
      muted:   s.getPropertyValue('--muted').trim(),
      rule:    s.getPropertyValue('--rule').trim(),
      bg2:     s.getPropertyValue('--bg2').trim()
    };
  }

  function isVisible(el) {
    return !!(el && el.offsetParent !== null && el.clientWidth > 0);
  }

  function ensure(id) {
    if (instances[id]) return instances[id];
    var builder = builders[id];
    if (!builder) return null;
    var el = document.getElementById(id);
    if (!isVisible(el)) return null;           // 不可见 → 暂不初始化
    if (typeof echarts === 'undefined') return null;
    var chart = echarts.init(el, null, { renderer: 'svg' });
    chart.setOption(builder(readVars()));
    instances[id] = chart;
    return chart;
  }

  function ensureVisible() {
    Object.keys(builders).forEach(function (id) {
      var el = document.getElementById(id);
      if (isVisible(el)) ensure(id);
    });
  }

  function resizeVisible() {
    Object.keys(instances).forEach(function (id) {
      var c = instances[id];
      if (!c) return;
      var el = document.getElementById(id);
      if (isVisible(el)) c.resize();
    });
  }

  function rebuildAll() {
    Object.keys(instances).forEach(function (id) {
      try { instances[id].dispose(); } catch (e) {}
      delete instances[id];
    });
    ensureVisible();
  }

  function def(id, builder) { builders[id] = builder; }

  window.WB_CHARTS = {
    builders: builders,
    instances: instances,
    ensure: ensure,
    ensureVisible: ensureVisible,
    resizeVisible: resizeVisible,
    rebuildAll: rebuildAll,
    def: def
  };

  /* ---------- 图 1 · 海外三强 ---------- */
  def('chart-overseas', function (v) {
    var radarCommon = radarBase(v);
    return Object.assign({}, radarCommon, {
      color: [v.accent, v.accent2, '#F59E0B', '#22A5F7'],
      series: [Object.assign({}, radarCommon.series[0], {
        data: [
          { name: 'GPT-5.6 Sol', value: [5.0, 4.5, 4.2, 4.5, 3.8, 5.0] },
          { name: 'Claude Fable 5', value: [4.9, 4.8, 4.0, 4.8, 3.2, 4.8] },
          { name: 'Gemini 3.5 Flash', value: [4.3, 4.0, 5.0, 5.0, 4.6, 4.5] }
        ]
      })]
    });
  });

  /* ---------- 图 2 · 国产四强 ---------- */
  def('chart-domestic', function (v) {
    var radarCommon = radarBase(v);
    return Object.assign({}, radarCommon, {
      color: [v.accent, v.accent2, '#F59E0B', '#6366F1'],
      series: [Object.assign({}, radarCommon.series[0], {
        data: [
          { name: 'DeepSeek V4-Pro', value: [4.6, 5.0, 3.0, 5.0, 5.0, 4.6] },
          { name: 'Kimi K3', value: [4.8, 4.4, 4.2, 5.0, 4.2, 5.0] },
          { name: 'Qwen3.8-Max', value: [4.5, 4.3, 5.0, 5.0, 4.8, 4.6] },
          { name: 'GLM-5.3', value: [4.6, 4.6, 3.6, 5.0, 4.4, 4.4] }
        ]
      })]
    });
  });

  /* ---------- 图 3 · SWE-bench Verified 横向柱状 ---------- */
  def('chart-swebench', function (v) {
    var swe = [
      { name: 'Claude Fable 5', value: 95.0 },
      { name: 'Claude Opus 4.8', value: 88.6 },
      { name: 'Gemini 3.1 Pro', value: 80.6 },
      { name: 'DeepSeek V4-Pro', value: 80.6 },
      { name: 'MiniMax M2.7', value: 80.2 },
      { name: 'Claude Sonnet 4.6', value: 79.6 }
    ];
    return {
      animation: false,
      tooltip: { appendToBody: true, valueFormatter: function (val) { return val + '%'; } },
      grid: { left: 130, right: 40, top: 20, bottom: 30 },
      xAxis: {
        type: 'value',
        max: 100,
        axisLabel: { color: v.muted, formatter: '{value}%' },
        splitLine: { lineStyle: { color: v.rule } }
      },
      yAxis: {
        type: 'category',
        data: swe.map(function (d) { return d.name; }).reverse(),
        axisLabel: { color: v.ink, fontSize: 12 },
        axisLine: { lineStyle: { color: v.rule } },
        axisTick: { show: false }
      },
      series: [{
        type: 'bar',
        data: swe.map(function (d) { return d.value; }).reverse(),
        barWidth: 18,
        itemStyle: {
          borderRadius: [0, 6, 6, 0],
          color: function (p) { return p.dataIndex === swe.length - 1 ? v.accent : v.accent2; }
        },
        label: {
          show: true,
          position: 'right',
          formatter: function (p) { return p.value + '%'; },
          color: v.muted,
          fontSize: 12
        }
      }]
    };
  });

  /* ---------- 雷达图公共底座 ---------- */
  function radarBase(v) {
    return {
      animation: false,
      tooltip: { appendToBody: true },
      legend: {
        bottom: 0,
        textStyle: { color: v.muted, fontSize: 12 },
        itemWidth: 14,
        itemHeight: 8
      },
      radar: {
        indicator: [
          { name: '编程 Coding', max: 5 },
          { name: '推理 Reasoning', max: 5 },
          { name: '多模态 Multimodal', max: 5 },
          { name: '长上下文 Long Ctx', max: 5 },
          { name: '性价比 Cost', max: 5 },
          { name: 'Agent 能力', max: 5 }
        ],
        radius: '64%',
        center: ['50%', '46%'],
        splitNumber: 4,
        axisName: { color: v.muted, fontSize: 12 },
        splitArea: { show: false },
        splitLine: { lineStyle: { color: v.rule } },
        axisLine: { lineStyle: { color: v.rule } }
      },
      series: [{ type: 'radar', symbolSize: 4, data: [] }]
    };
  }

  /* ---------- 窗口尺寸变化 ---------- */
  window.addEventListener('resize', resizeVisible);

  /* ---------- 主题切换：销毁重建，配色跟随 CSS 变量 ---------- */
  if (window.MutationObserver) {
    var lastTheme = document.documentElement.getAttribute('data-theme');
    new MutationObserver(function () {
      var now = document.documentElement.getAttribute('data-theme');
      if (now === lastTheme) return;
      lastTheme = now;
      setTimeout(rebuildAll, 60);
    }).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
  }
})();
