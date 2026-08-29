/* 模型页 · 图表脚本
 *
 * 设计要点：
 * 1. 图表只注册「构造 option 的函数」，不立即 echarts.init。
 *    图表位于隐藏页签内时容器尺寸为 0，立即 init 会得到 0×0 画布；
 *    改为切到该页时再 ensure() 真正初始化。
 * 2. 所有图表统一支持「点击下钻」：数据项带 idx（MODELS 数组下标），
 *    点击后调用 window.WB_DRILL(idx) 打开模型详情弹窗。
 * 3. 数据来自 models.html 注入的 window.WB_MATRIX / window.WB_IDX，
 *    本文件不硬编码模型清单，改数据只需改 models.html。
 *
 * 对外暴露 window.WB_CHARTS：
 *   .def(id, builder)      注册 option 构造函数
 *   .ensure(id)            初始化（不可见则跳过）
 *   .ensureVisible()       初始化当前所有可见图表
 *   .resizeVisible()       对已初始化且可见的图表 resize
 *   .rebuildAll()          主题切换后销毁重建，配色跟随 CSS 变量
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
      bg:      s.getPropertyValue('--bg').trim(),
      bg2:     s.getPropertyValue('--bg2').trim()
    };
  }

  function isVisible(el) {
    return !!(el && el.offsetParent !== null && el.clientWidth > 0);
  }

  /* 绑定统一的下钻点击：数据项可带 idx 字段，或数组第 4 位存 idx */
  function bindDrill(chart) {
    chart.on('click', function (p) {
      var idx = null;
      if (p.data && p.data.idx != null) idx = p.data.idx;
      else if (Array.isArray(p.value) && p.value.length > 3) idx = p.value[3];
      if (idx != null && typeof window.WB_DRILL === 'function') window.WB_DRILL(idx);
    });
  }

  function ensure(id) {
    if (instances[id]) return instances[id];
    var builder = builders[id];
    if (!builder) return null;
    var el = document.getElementById(id);
    if (!isVisible(el)) return null;
    if (typeof echarts === 'undefined') return null;
    var chart = echarts.init(el, null, { renderer: 'svg' });
    chart.setOption(builder(readVars()));
    bindDrill(chart);
    instances[id] = chart;
    return chart;
  }

  /* 只初始化「可见」的图表；若浏览器支持 IntersectionObserver，
   * 再进一步只在容器滚动进视口时才真正渲染，避免首屏一次性渲染多张大图。 */
  var io = null;
  if (window.IntersectionObserver) {
    io = new window.IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (!en.isIntersecting) return;
        io.unobserve(en.target);
        ensure(en.target.id);
      });
    }, { rootMargin: '200px 0px' });
  }

  function ensureVisible() {
    Object.keys(builders).forEach(function (id) {
      if (instances[id]) return;
      var el = document.getElementById(id);
      if (!isVisible(el)) return;
      if (io) io.observe(el);
      else ensure(id);
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

  /* 重新构建某一个图表（分组切换时用） */
  function rebuild(id) {
    if (instances[id]) {
      try { instances[id].dispose(); } catch (e) {}
      delete instances[id];
    }
    return ensure(id);
  }

  function def(id, builder) { builders[id] = builder; }

  window.WB_CHARTS = {
    builders: builders,
    instances: instances,
    def: def,
    ensure: ensure,
    rebuild: rebuild,
    ensureVisible: ensureVisible,
    resizeVisible: resizeVisible,
    rebuildAll: rebuildAll
  };

  /* =========================================================
   * 图 1 · 能力热力图（32 个模型 × 5 个维度）
   * ======================================================= */
  def('chart-heatmap', function (v) {
    var m = window.WB_MATRIX || { dims: [], rows: [] };
    var heat = [];
    m.rows.forEach(function (r, y) {
      r.scores.forEach(function (s, x) {
        heat.push([x, y, s, r.idx]);   // 第 4 位存 MODELS 下标，供下钻
      });
    });
    return {
      animation: false,
      tooltip: {
        appendToBody: true,
        formatter: function (p) {
          var row = m.rows[p.value[1]];
          if (!row) return '';
          return '<b>' + row.name + '</b><br/>' +
            m.dims[p.value[0]] + '：<b>' + p.value[2] + '</b> / 5<br/>' +
            '<span style="opacity:.7">点击查看完整解读</span>';
        }
      },
      grid: { left: 148, right: 24, top: 34, bottom: 46 },
      xAxis: {
        type: 'category',
        data: m.dims,
        position: 'top',
        splitArea: { show: true },
        axisLabel: { color: v.ink, fontSize: 12, fontWeight: 600 },
        axisLine: { lineStyle: { color: v.rule } },
        axisTick: { show: false }
      },
      yAxis: {
        type: 'category',
        data: m.rows.map(function (r) { return r.name; }),
        inverse: true,                    // 综合分最高的排在最上面
        splitArea: { show: true },
        axisLabel: { color: v.muted, fontSize: 11.5 },
        axisLine: { lineStyle: { color: v.rule } },
        axisTick: { show: false }
      },
      visualMap: {
        min: 1,
        max: 5,
        calculable: true,
        orient: 'horizontal',
        left: 'center',
        bottom: 4,
        itemWidth: 12,
        itemHeight: 90,
        textStyle: { color: v.muted, fontSize: 11 },
        inRange: { color: ['#F3F6F4', '#A7DBC6', '#4FBB8C', '#1E8F63', '#0B6B4A'] }
      },
      series: [{
        type: 'heatmap',
        data: heat,
        label: {
          show: true,
          formatter: function (p) { return p.value[2]; },
          fontSize: 10.5,
          color: '#fff'
        },
        itemStyle: { borderColor: v.bg, borderWidth: 1.5, borderRadius: 3 },
        emphasis: {
          itemStyle: { borderColor: v.accent, borderWidth: 2.5, shadowBlur: 6, shadowColor: 'rgba(0,0,0,.25)' }
        }
      }]
    };
  });

  /* =========================================================
   * 图 2 · 能力 vs 性价比 定位散点图
   * ======================================================= */
  def('chart-scatter', function (v) {
    var m = window.WB_MATRIX || { rows: [] };
    var groups = window.WB_GROUPS || [];
    var series = groups.map(function (g) {
      var pts = m.rows.filter(function (r) { return r.cat === g.key; });
      return {
        name: g.label,
        type: 'scatter',
        symbolSize: 17,
        data: pts.map(function (r) {
          var ability = (r.scores[0] + r.scores[1] + r.scores[2] + r.scores[3]) / 4;
          return { value: [r.scores[4], +ability.toFixed(2)], name: r.name, idx: r.idx };
        }),
        itemStyle: {
          color: g.color,
          opacity: 0.82,
          borderColor: v.bg,
          borderWidth: 1
        },
        label: {
          show: true,
          position: 'right',
          formatter: '{b}',
          fontSize: 10.5,
          color: v.muted,
          distance: 6
        },
        labelLayout: { hideOverlap: true },
        emphasis: { itemStyle: { opacity: 1, borderColor: v.accent, borderWidth: 2 }, scale: 1.35 }
      };
    });

    return {
      animation: false,
      tooltip: {
        appendToBody: true,
        formatter: function (p) {
          var r = null;
          for (var i = 0; i < m.rows.length; i++) if (m.rows[i].idx === p.data.idx) { r = m.rows[i]; break; }
          if (!r) return p.name;
          return '<b>' + r.name + '</b>（' + r.vendor + '）<br/>' +
            '能力 ' + p.value[1] + ' / 5　性价比 ' + p.value[0] + ' / 5<br/>' +
            '<span style="opacity:.7">点击查看完整解读</span>';
        }
      },
      legend: {
        bottom: 0,
        textStyle: { color: v.muted, fontSize: 12 },
        itemWidth: 12,
        itemHeight: 12
      },
      grid: { left: 52, right: 34, top: 26, bottom: 52 },
      xAxis: {
        name: '性价比 →（越右越便宜）',
        nameLocation: 'middle',
        nameGap: 28,
        nameTextStyle: { color: v.muted, fontSize: 11.5 },
        type: 'value',
        min: 1.5,
        max: 5.6,
        interval: 0.5,
        axisLabel: { color: v.muted, fontSize: 11 },
        splitLine: { lineStyle: { color: v.rule, type: 'dashed' } },
        axisLine: { show: false }
      },
      yAxis: {
        name: '能力 →（越上越强）',
        nameTextStyle: { color: v.muted, fontSize: 11.5 },
        type: 'value',
        min: 1.5,
        max: 5.4,
        interval: 0.5,
        axisLabel: { color: v.muted, fontSize: 11 },
        splitLine: { lineStyle: { color: v.rule, type: 'dashed' } },
        axisLine: { show: false }
      },
      series: series
    };
  });

  /* =========================================================
   * 图 3 · 旗舰能力画像雷达（分组可切换）
   * ======================================================= */
  var RADAR_GROUPS = {
    overseas: {
      color: [null, null, '#F59E0B'],
      data: [
        { name: 'GPT-5.6 Sol',        value: [5.0, 4.5, 4.2, 4.5, 3.8, 5.0] },
        { name: 'Claude Fable 5',     value: [4.9, 4.8, 4.0, 4.8, 3.2, 4.8] },
        { name: 'Gemini 3.5 Flash',   value: [4.3, 4.0, 5.0, 5.0, 4.6, 4.5] }
      ]
    },
    domestic: {
      color: [null, null, '#F59E0B', '#6366F1'],
      data: [
        { name: 'DeepSeek V4-Pro',    value: [4.6, 5.0, 3.0, 5.0, 5.0, 4.6] },
        { name: 'Kimi K3',            value: [4.8, 4.4, 4.2, 5.0, 4.2, 5.0] },
        { name: 'Qwen3.8-Max',        value: [4.5, 4.3, 5.0, 5.0, 4.8, 4.6] },
        { name: 'GLM-5.3',            value: [4.6, 4.6, 3.6, 5.0, 4.4, 4.4] }
      ]
    }
  };

  /* 名字 → MODELS 下标的模糊映射（雷达图用的是"产品名"，MODELS 里是"系列名"） */
  var RADAR_ALIAS = {
    'GPT-5.6 Sol': 'GPT-5.6 系列',
    'Claude Fable 5': 'Claude Fable 5',
    'Gemini 3.5 Flash': 'Gemini 3.5 / 3.6 Flash',
    'DeepSeek V4-Pro': 'DeepSeek V4',
    'Kimi K3': 'Kimi K3',
    'Qwen3.8-Max': 'Qwen3.8-Max',
    'GLM-5.3': '智谱 GLM-5.3'
  };

  window.WB_RADAR = { group: 'overseas' };

  def('chart-radar', function (v) {
    var g = RADAR_GROUPS[window.WB_RADAR.group] || RADAR_GROUPS.overseas;
    var idxMap = window.WB_IDX || {};
    var colors = g.color.map(function (c, i) {
      return c || (i === 0 ? v.accent : v.accent2);
    });
    return radarBase(v, {
      color: colors,
      data: g.data.map(function (d) {
        return {
          name: d.name,
          value: d.value,
          idx: idxMap[RADAR_ALIAS[d.name] || d.name]
        };
      })
    });
  });

  function radarBase(v, extra) {
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
          { name: '多模态', max: 5 },
          { name: '长上下文', max: 5 },
          { name: '性价比', max: 5 },
          { name: 'Agent 能力', max: 5 }
        ],
        radius: '62%',
        center: ['50%', '45%'],
        splitNumber: 4,
        axisName: { color: v.muted, fontSize: 12 },
        splitArea: { show: false },
        splitLine: { lineStyle: { color: v.rule } },
        axisLine: { lineStyle: { color: v.rule } }
      },
      series: [{
        type: 'radar',
        symbolSize: 6,
        areaStyle: { opacity: 0.08 },
        lineStyle: { width: 2 },
        data: extra.data
      }],
      color: extra.color
    };
  }

  /* =========================================================
   * 图 4 · SWE-bench Verified 实测（真实基准分）
   * ======================================================= */
  var SWE_ALIAS = {
    'Claude Fable 5': 'Claude Fable 5',
    'Claude Opus 4.8': null,
    'Gemini 3.1 Pro': 'Gemini 3.1 Pro',
    'DeepSeek V4-Pro': 'DeepSeek V4',
    'MiniMax M2.7': 'MiniMax M2.7',
    'Claude Sonnet 4.6': null
  };

  def('chart-swebench', function (v) {
    var swe = [
      { name: 'Claude Fable 5', value: 95.0 },
      { name: 'Claude Opus 4.8', value: 88.6 },
      { name: 'Gemini 3.1 Pro', value: 80.6 },
      { name: 'DeepSeek V4-Pro', value: 80.6 },
      { name: 'MiniMax M2.7', value: 80.2 },
      { name: 'Claude Sonnet 4.6', value: 79.6 }
    ];
    var idxMap = window.WB_IDX || {};
    var asc = swe.slice().sort(function (a, b) { return a.value - b.value; });
    return {
      animation: false,
      tooltip: {
        appendToBody: true,
        formatter: function (p) {
          var extra = (p.data && p.data.idx != null)
            ? '<br/><span style="opacity:.7">点击查看完整解读</span>' : '';
          return p.name + '：<b>' + p.value + '%</b>' + extra;
        }
      },
      grid: { left: 132, right: 56, top: 14, bottom: 24 },
      xAxis: {
        type: 'value',
        max: 100,
        axisLabel: { color: v.muted, formatter: '{value}%' },
        splitLine: { lineStyle: { color: v.rule } }
      },
      yAxis: {
        type: 'category',
        data: asc.map(function (d) { return d.name; }),
        axisLabel: { color: v.ink, fontSize: 12 },
        axisLine: { lineStyle: { color: v.rule } },
        axisTick: { show: false }
      },
      series: [{
        type: 'bar',
        data: asc.map(function (d) {
          var alias = SWE_ALIAS[d.name];
          return {
            value: d.value,
            idx: alias ? idxMap[alias] : null,
            itemStyle: {
              borderRadius: [0, 6, 6, 0],
              color: d.value >= 90 ? v.accent : v.accent2
            }
          };
        }),
        barWidth: 18,
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
