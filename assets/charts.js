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
    var out = {
      accent:  s.getPropertyValue('--accent').trim(),
      accent2: s.getPropertyValue('--accent2').trim(),
      ink:     s.getPropertyValue('--ink').trim(),
      muted:   s.getPropertyValue('--muted').trim(),
      faint:   s.getPropertyValue('--faint').trim(),
      rule:    s.getPropertyValue('--rule').trim(),
      bg:      s.getPropertyValue('--bg').trim(),
      bg2:     s.getPropertyValue('--bg2').trim(),
      // 移动端判定：CSS 的 640px 断点与之呼应（见 app.css 的 .is-mobile 相关规则）
      mobile:  window.matchMedia ? window.matchMedia('(max-width: 640px)').matches
                                 : (window.innerWidth <= 640)
    };
    // 厂商配色：--chart-c1..c12，两套主题各有一份（亮色高饱和 / 暗色高亮）
    out.palette = [];
    for (var i = 1; i <= 12; i++) {
      var c = s.getPropertyValue('--chart-c' + i).trim();
      if (c) out.palette.push(c);
    }
    if (!out.palette.length) {
      out.palette = ['#059669', '#2563EB', '#D97706', '#7C3AED', '#0891B2',
                     '#DB2777', '#65A30D', '#EA580C', '#4F46E5', '#0D9488',
                     '#C026D3', '#B45309'];
    }
    return out;
  }

  function isVisible(el) {
    return !!(el && el.offsetParent !== null && el.clientWidth > 0);
  }

  /* =========================================================
   * 热力图专用：固定 Y 轴列（2026-09-11）
   * 需求：手机上左右滑动看 5 个维度时，最左侧的模型名列表要钉住不动。
   *
   * 实现：把原来"一张图"拆成两段 ——
   *   左：.heat-y-axis（自绘 DOM 标签列，flex:none）
   *   右：.heat-scroll > #chart-heatmap（ECharts 只画格子 + 顶部维度标签）
   *
   * ⚠️ 关键（第一版写错、已修正）：
   *   这两段是**兄弟节点**，左列根本不在滚动容器里，**本来就静止**。
   *   所以不需要任何"滚动同步"——第一版画蛇添足加了
   *   `transform: translateX(scrollLeft)`，结果一滑模型名就往右跑出左列、
   *   被 .heat-wrap 的 overflow:hidden 裁掉。**别再加回来。**
   *   唯一要做的是让两列行高对齐（由 measureHeat 实测后写入内联样式）。
   * ======================================================= */

  // 行高 / 上下留白：与 buildHeatOption 里的 grid 保持一致（见该函数 grid 段）
  var HEAT_ROW_H   = 34;   // 每行格子高度（仅作初始估算，实际以 ECharts 反推为准）
  var HEAT_TOP     = 56;   // 绘图区距画布顶部的距离（够放竖排的维度名）
  var HEAT_BOTTOM  = 38;   // 绘图区距画布底部的距离（要放得下 x 轴标签 ~12px + 色阶图例 ~22px + 间隙）
  // ⚠️ 移动端与桌面端**必须共用同一个 HEAT_BOTTOM** ——
  //    measureHeat / renderHeatYAxis 是按它反推行高的，两边不一致就会错位。
  //    移动端虽然隐藏了图例，多留这点空白无妨，不要为了省空间拆成两个值。

  // ECharts 实测反推出的每行占用高度
  var heatPitch   = HEAT_ROW_H;
  var heatOffsetY = HEAT_TOP;   // 绘图区顶边相对画布顶部的像素偏移

  function heatRowPitch() { return heatPitch; }

  // 每行的最小高度：文字最多两行 ≈ 11.5×1.18×2 ≈ 27px，留点余量取 32
  var HEAT_MIN_PITCH = 32;

  /**
   * 从 ECharts 实例里读出绘图区真实位置，反推每行占用的高度。
   * 为什么必须这么做：ECharts 的类目行高是「绘图区高度 ÷ 行数」自动算的，
   * 用常量估算必然累积误差 —— 10 行下来能错位十几像素，左列和格子就对不上了。
   *
   * 另外做「行高下限保护」：画布不够高时主动撑高容器再 resize。
   * 这样容器被压缩、或将来模型从 10 个增加到更多时，行都不会挤成一团。
   */
  function measureHeat(chart) {
    if (!chart) return;
    try {
      var m = window.WB_MATRIX || { rows: [] };
      var n = (m.rows || []).length;
      if (!n) return;

      var el = chart.getDom ? chart.getDom() : null;
      var h = chart.getHeight();

      // 行高下限保护：不够就把画布撑到刚好够
      var need = HEAT_MIN_PITCH * n + HEAT_TOP + HEAT_BOTTOM;
      if (el && h && h < need) {
        el.style.minHeight = need + 'px';
        chart.resize();
        h = chart.getHeight() || need;
      }
      if (!h) return;

      var plotH = h - HEAT_TOP - HEAT_BOTTOM;   // 绘图区高度
      heatOffsetY = HEAT_TOP;
      heatPitch = plotH / n;
    } catch (e) {}
    renderHeatYAxis();
  }

  /** 渲染／刷新左侧固定列。幂等，可反复调用。 */
  function renderHeatYAxis() {
    var host = document.querySelector('.heat-y-axis');
    if (!host) return;
    var m = window.WB_MATRIX || { rows: [] };
    var pitch = heatRowPitch();

    host.style.paddingTop = heatOffsetY + 'px';
    host.style.paddingBottom = HEAT_BOTTOM + 'px';

    var inner = host.querySelector('.heat-y-axis__inner');
    if (!inner) {
      inner = document.createElement('div');
      inner.className = 'heat-y-axis__inner';
      host.appendChild(inner);
    }

    // 内容 + 行高都没变则不重建，避免滚动中被打断
    var want = m.rows.map(function (r) { return r.idx + '|' + r.name; }).join('~') + '@' + pitch;
    if (inner.getAttribute('data-sig') === want) return;
    inner.setAttribute('data-sig', want);

    inner.innerHTML = m.rows.map(function (r) {
      return '<div class="heat-y-axis__row" data-idx="' + r.idx + '"' +
        ' style="height:' + pitch + 'px" title="' + r.name + '">' +
        '<span>' + r.name + '</span></div>';
    }).join('');

    // 点模型名也能下钻，与点格子一致
    inner.querySelectorAll('.heat-y-axis__row').forEach(function (el) {
      el.addEventListener('click', function () {
        var idx = +el.getAttribute('data-idx');
        if (typeof window.WB_DRILL === 'function') window.WB_DRILL(idx);
      });
    });
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
    // 热力图：先备好左列固定标签 + 确定画布逻辑宽度，再 init
    if (id === 'chart-heatmap') {
      renderHeatYAxis();
      applyMinWidth(id, HEAT_WIDE);
    }
    var chart = echarts.init(el, null, { renderer: 'svg' });
    chart.setOption(builder(readVars()));
    bindDrill(chart);
    instances[id] = chart;
    // 热力图：渲染完成后按实测绘图区反推行高，再对齐左侧固定列
    if (id === 'chart-heatmap') measureHeat(chart);
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
      if (!isVisible(el)) return;
      // 热力图在两屏宽度之间切换时要重设逻辑宽度，否则会留下上一次的固定宽度
      if (id === 'chart-heatmap') applyMinWidth(id, HEAT_WIDE);
      c.resize();
      // resize 后行高会变，需要重新测量并对齐左列
      if (id === 'chart-heatmap') measureHeat(c);
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

  /* 窄屏下把图表画布撑到指定逻辑宽度，让外层容器横向滚动 ——
   * 这是"手机上也能看全"的关键：ECharts 会按这个宽度布局，
   * 用户左右滑动查看，而不是把 5 列 + 长标签硬压进 375px。
   *
   * 2026-09-11 起热力图改用「左列固定 + 右侧滚动」：
   * 画布宽度只算「格子区 + 两侧留白」，**不含 Y 轴标签宽度**
   * （标签已经搬到左列 DOM 里去了），否则会白留一大块空白。 */
  function applyMinWidth(id, minW) {
    var el = document.getElementById(id);
    if (!el) return;
    var wrap = el.parentElement;
    var mobile = window.matchMedia && window.matchMedia('(max-width: 640px)').matches;
    var w = minW;
    if (id === 'chart-heatmap') {
      // 桌面端左列与画布同宽，无需滚动；窄屏才钉住宽度
      var fixed = 0;
      var axis = document.querySelector('.heat-y-axis');
      if (axis) fixed = axis.offsetWidth || 0;
      if (mobile && fixed) w = minW - fixed;
    }
    if (mobile) {
      el.style.width = w + 'px';
      el.style.minWidth = w + 'px';
    } else {
      el.style.width = '';
      el.style.minWidth = '';
      // 回到桌面布局：清掉可能的滚动残值
      if (id === 'chart-heatmap' && wrap) wrap.scrollLeft = 0;
    }
    // heat-scroll 始终挂上：桌面端靠它的 overflow:hidden 裁掉溢出，
    // 窄屏再由 media query 切成 overflow-x:auto。两边都需要这个类，别只在窄屏加。
    if (wrap && id === 'chart-heatmap') wrap.classList.add('heat-scroll');
  }

  window.WB_CHARTS = {
    builders: builders,
    instances: instances,
    def: def,
    ensure: ensure,
    rebuild: rebuild,
    ensureVisible: ensureVisible,
    resizeVisible: resizeVisible,
    rebuildAll: rebuildAll,
    applyMinWidth: applyMinWidth,
    renderHeatYAxis: renderHeatYAxis
  };

  /* =========================================================
   * 图 1 · 能力热力图（10 个国产主力 × 5 维）
   *
   * 三个关键设计：
   * ① 移动端不做"压缩"，做"横向滚动"。手机宽 ~375px 塞 5 列 + 10 行长标签，
   *    字会小到看不清。改为在窄屏把画布宽度撑到 HEAT_WIDE，外层容器滚动查看。
   * ② **Y 轴标签搬到左边的固定列**（.heat-y-axis），不参与横向滚动 ——
   *    左右滑动看维度时，模型名始终可见（用户 2026-09-11 提的需求）。
   *    因此本图的 grid.left/right 只留一点点内边距，不再为标签预留宽度。
   * ③ 配色改为深底霓虹（科技感），且亮度随分值单调递增，方便扫列找最强项。
   * ======================================================= */
  var HEAT_WIDE = 760;   // 窄屏下「左列 + 格子区」的总宽（左列宽度由 applyMinWidth 扣除）

  def('chart-heatmap', function (v) {
    var m = window.WB_MATRIX || { dims: [], rows: [] };
    var heat = [];
    m.rows.forEach(function (r, y) {
      r.scores.forEach(function (s, x) {
        heat.push([x, y, s, r.idx]);   // 第 4 位存 MODELS 下标，供下钻
      });
    });

    var dims = m.dims;
    var mobile = v.mobile;
    // 移动端：标签竖排；桌面：保持水平标签
    var xLabels = mobile
      ? dims.map(function (d) { return d.split('').join('\n'); })
      : dims;
    var labelFont = mobile ? 11 : 12;
    // Y 轴标签已在左侧固定列，画布两侧只留少量内边距
    var gridLeft = 8;
    var gridRight = 10;

    /* 分值 → 颜色：1..5 映射到 深空蓝 → 青 → 亮绿（越强越亮，暗底上很直观） */
    var RAMP = ['#12303F', '#175B57', '#1E8F6B', '#2FD08A', '#7BF7C4'];
    function colorOf(s) {
      var i = Math.max(0, Math.min(4, Math.round(s) - 1));
      return RAMP[i];
    }
    function inkOf(s) { return s >= 4 ? '#062018' : '#DDF6EC'; }

    return {
      animation: false,
      // 深色图面：与整体浅色页面形成"仪表盘"对比，科技感来源之一
      backgroundColor: 'transparent',
      tooltip: {
        appendToBody: true,
        backgroundColor: 'rgba(6, 24, 20, .94)',
        borderColor: 'rgba(47, 208, 138, .55)',
        borderWidth: 1,
        textStyle: { color: '#E4F5EC', fontSize: 13 },
        formatter: function (p) {
          var row = m.rows[p.value[1]];
          if (!row) return '';
          var d = dims[p.value[0]];
          var bar = '▮'.repeat(p.value[2]) + '▯'.repeat(5 - p.value[2]);
          return '<b>' + row.name + '</b>　<span style="opacity:.65">' + row.vendor + '</span><br/>' +
            d + '：<b>' + p.value[2] + '</b> / 5　<span style="color:#2FD08A;letter-spacing:1px">' + bar + '</span><br/>' +
            '<span style="opacity:.6">点击查看完整解读</span>';
        }
      },
      grid: {
        left: gridLeft, right: gridRight,
        top: HEAT_TOP,
        bottom: HEAT_BOTTOM
      },
      xAxis: {
        type: 'category',
        data: xLabels,
        position: 'top',
        splitArea: { show: false },
        axisLabel: {
          color: v.ink, fontSize: labelFont, fontWeight: 700,
          lineHeight: mobile ? 13 : 16
        },
        axisLine: { lineStyle: { color: 'rgba(47, 208, 138, .35)' } },
        axisTick: { show: false }
      },
      yAxis: {
        type: 'category',
        data: m.rows.map(function (r) { return r.name; }),
        inverse: true,                    // 综合分最高的排在最上面
        splitArea: { show: false },
        // 标签由左侧固定列渲染（见 renderHeatYAxis），这里彻底关掉
        axisLabel: { show: false },
        axisLine: { show: false },
        axisTick: { show: false }
      },
      visualMap: {
        min: 1,
        max: 5,
        calculable: false,
        show: !mobile,                    // 移动端空间紧张，隐藏色条（颜色自解释）
        orient: 'horizontal',
        left: 'center',
        bottom: 6,
        // ⚠️ ECharts 的 itemWidth/itemHeight 语义【不随 orient 交换】：
        //    itemWidth 永远是「厚度」（horizontal 时即竖直方向），
        //    itemHeight 永远是「长度」（horizontal 时即水平方向）。
        //    内部先按 itemWidth×itemHeight 画矩形再旋转 90°（SVG 实测 transform
        //    matrix(0,-1,1,0,…)）。所以 horizontal 想要「长132×厚9的横条」，
        //    必须写 itemWidth:9, itemHeight:132 —— 写成 132×9 会渲染成竖杠（v24 踩坑）。
        itemWidth: 9,
        itemHeight: 132,
        text: ['强', '弱'],
        textStyle: { color: v.muted, fontSize: 11 },
        inRange: { color: RAMP }
      },
      series: [{
        type: 'heatmap',
        data: heat,
        label: {
          show: true,
          formatter: function (p) { return p.value[2]; },
          fontSize: mobile ? 11 : 11.5,
          fontWeight: 700,
          color: function (p) { return inkOf(p.value[2]); }
        },
        itemStyle: {
          borderColor: 'rgba(244, 251, 247, .16)',
          borderWidth: 2,
          borderRadius: 5
        },
        emphasis: {
          itemStyle: {
            borderColor: '#7BF7C4',
            borderWidth: 2.5,
            shadowBlur: 16,
            shadowColor: 'rgba(47, 208, 138, .85)'
          }
        },
        // 逐格上色（visualMap 已给统一的 inRange，这里再显式覆盖以保证两主题一致）
        progressive: 0
      }]
    };
  });

  /* =========================================================
   * 图 2 · 能力 vs 性价比 定位散点图
   *
   * 重构要点（2026-09-11）：
   * ① 分组从「阵营」改为「厂商」—— 只收国产通用大模型后 4 个阵营里 3 个没数据，
   *    原来图例只有 1 项、点全同色，看起来就是"糊在一起"。现在每厂一色 + 图例。
   * ② 移动端把图例竖排到右侧会挤扁绘图区，改为底部横排 + 缩小点径/字号；
   *    同时把标签引线关掉、只显示圆点，避免小屏上标签互相压住（点仍可点开）。
   * ③ 右上"甜点区"用 markArea 打一层淡光，一眼看出该选谁。
   * ======================================================= */
  def('chart-scatter', function (v) {
    var m = window.WB_MATRIX || { rows: [] };
    var groups = (typeof window.WB_SCATTER_GROUPS === 'function')
      ? window.WB_SCATTER_GROUPS()
      : (window.WB_GROUPS || []);
    var pal = v.palette || [];
    var mobile = v.mobile;

    // 能力 = 前四维均值；性价比 = 第五维
    function ability(r) {
      return +((r.scores[0] + r.scores[1] + r.scores[2] + r.scores[3]) / 4).toFixed(2);
    }
    /* 坐标轴按实际数据动态收窄 —— 这是散点图不再挤成一团的关键。
     * 评分都是 1-5 分制，但实际只落在 3.4~5 这个窄区间；若轴仍按 1.5~5.6 铺满，
     * 所有点会压成中间一条横带，看上去就是"全都重叠在一起"。 */
    function range(vals, pad, step) {
      if (!vals.length) return { min: 0, max: 5 };
      var lo = Math.min.apply(null, vals) - pad;
      var hi = Math.max.apply(null, vals) + pad;
      return { min: Math.floor(lo / step) * step, max: Math.ceil(hi / step) * step };
    }
    var rx = range(m.rows.map(function (r) { return r.scores[4]; }), 0.4, 0.5);
    var ry = range(m.rows.map(ability), 0.25, 0.25);

    /* 坐标完全相同的点沿 Y 轴做极小错位，让每个圆点都能露出来。
     * 例如文心 5.1 与阶跃 Step 3.7 的（性价比 4, 能力 3.875）一模一样，
     * 不处理的话后画的点会把前一个整个盖住，看上去只有一个点。
     * 偏移量只取 Y 轴跨度的 2.5%（约 0.04 分），肉眼几乎不可辨，
     * 且只作用于图形位置 —— tooltip 里显示的仍是原始分数。 */
    var jitter = (ry.max - ry.min) * 0.025;
    var buckets = {};
    m.rows.forEach(function (r) {
      var k = r.scores[4] + '|' + ability(r);
      (buckets[k] = buckets[k] || []).push(r.idx);
    });
    var offset = {};
    Object.keys(buckets).forEach(function (k) {
      var g = buckets[k];
      if (g.length < 2) return;
      g.forEach(function (idx, i) { offset[idx] = (i - (g.length - 1) / 2) * jitter; });
    });

    var series = groups.map(function (g, gi) {
      var pts = m.rows.filter(function (r) { return r.vendor === g.key; });
      if (!pts.length) return null;   // 该分组没有点时整组跳过，避免图例出现空项
      var color = pal[gi % (pal.length || 1)] || v.accent;
      return {
        name: g.label,
        type: 'scatter',
        symbolSize: mobile ? 14 : 15,
        data: pts.map(function (r) {
          var y = +(ability(r) + (offset[r.idx] || 0)).toFixed(3);
          return { value: [r.scores[4], y], name: r.name, idx: r.idx };
        }),
        itemStyle: {
          color: color,
          opacity: 0.9,
          borderColor: '#FFFFFF',
          borderWidth: 1.4,
          shadowBlur: 10,
          shadowColor: 'rgba(0, 0, 0, .16)'
        },
        // 桌面端显示引线标签；移动端空间不够，只在悬停/点击时给提示
        label: mobile ? { show: false } : {
          show: true,
          // 按归一化高度朝外发散：上半区标签落点下方、下半区落上方，减少同向堆叠
          position: function (p) {
            var span = (ry.max - ry.min) || 1;
            var norm = (p.value[1] - ry.min) / span;
            return norm > 0.5 ? 'bottom' : 'top';
          },
          formatter: '{b}',
          fontSize: 10.5,
          color: v.ink,
          backgroundColor: v.bg2,
          borderColor: color,
          borderWidth: 1,
          padding: [2, 5],
          borderRadius: 4,
          distance: 6
        },
        labelLine: mobile ? { show: false } : {
          show: true, length: 8, length2: 10,
          lineStyle: { color: v.muted, width: 1, opacity: 0.5 }
        },
        // 全部显示（hideOverlap:false），拥挤处由 moveOverlap 竖向避让；标签带引线指向圆点
        labelLayout: { hideOverlap: false, moveOverlap: 'shiftY' },
        emphasis: {
          itemStyle: { opacity: 1, borderColor: v.accent, borderWidth: 2.5, shadowBlur: 18, shadowColor: v.accent },
          scale: 1.4
        },
        markArea: gi === 0 ? {
          silent: true,
          itemStyle: { color: 'rgba(47, 208, 138, .10)' },
          label: {
            show: true,
            position: 'insideTopRight',
            formatter: '★ 甜点区\n又强又便宜',
            color: '#0B6B4A',
            fontSize: mobile ? 10 : 11.5,
            fontWeight: 700,
            lineHeight: 14
          },
          // 右上角 1/4 区域
          data: [[{ xAxis: rx.max - (rx.max - rx.min) / 2, yAxis: ry.max - (ry.max - ry.min) / 2 },
                  { xAxis: rx.max, yAxis: ry.max }]]
        } : null
      };
    }).filter(Boolean);

    var legendData = series.map(function (s) { return s.name; });

    return {
      animation: false,
      tooltip: {
        appendToBody: true,
        backgroundColor: 'rgba(6, 24, 20, .94)',
        borderColor: 'rgba(47, 208, 138, .55)',
        borderWidth: 1,
        textStyle: { color: '#E4F5EC', fontSize: 13 },
        formatter: function (p) {
          var r = null;
          for (var i = 0; i < m.rows.length; i++) if (m.rows[i].idx === p.data.idx) { r = m.rows[i]; break; }
          if (!r) return p.name;
          // 注意用 ability(r) / r.scores[4] 取原始分，不用 p.value —— 后者可能带过重合错位量
          return '<b>' + r.name + '</b>　<span style="opacity:.65">' + r.vendor + '</span><br/>' +
            '能力 <b>' + ability(r) + '</b> / 5<br/>性价比 <b>' + r.scores[4] + '</b> / 5<br/>' +
            '<span style="opacity:.6">点击查看完整解读</span>';
        }
      },
      legend: mobile ? {
        type: 'scroll',
        bottom: 0,
        left: 'center',
        itemWidth: 10,
        itemHeight: 10,
        itemGap: 10,
        textStyle: { color: v.muted, fontSize: 10.5 },
        data: legendData
      } : {
        bottom: 0,
        left: 'center',
        itemWidth: 11,
        itemHeight: 11,
        itemGap: 16,
        textStyle: { color: v.muted, fontSize: 12 },
        data: legendData
      },
      grid: mobile
        ? { left: 46, right: 16, top: 44, bottom: 78 }
        : { left: 58, right: 40, top: 34, bottom: 62 },
      xAxis: {
        name: mobile ? '性价比 →' : '性价比 →（越右越便宜）',
        nameLocation: 'middle',
        nameGap: mobile ? 22 : 28,
        nameTextStyle: { color: v.muted, fontSize: mobile ? 10.5 : 11.5, fontWeight: 600 },
        type: 'value',
        min: rx.min,
        max: rx.max,
        interval: 0.5,
        axisLabel: { color: v.muted, fontSize: mobile ? 10 : 11 },
        splitLine: { lineStyle: { color: v.rule, type: 'dashed' } },
        axisLine: { show: false }
      },
      yAxis: {
        name: mobile ? '能力 →' : '能力 →（越上越强）',
        nameGap: mobile ? 8 : 12,
        nameTextStyle: { color: v.muted, fontSize: mobile ? 10.5 : 11.5, fontWeight: 600 },
        type: 'value',
        min: ry.min,
        max: ry.max,
        interval: 0.25,
        axisLabel: {
          color: v.muted, fontSize: mobile ? 10 : 11,
          formatter: function (n) { return mobile ? n.toFixed(1) : n.toFixed(2); }
        },
        splitLine: { lineStyle: { color: v.rule, type: 'dashed' } },
        axisLine: { show: false }
      },
      series: series
    };
  });

  /* =========================================================
   * 图 3 · 国产旗舰能力画像雷达
   * 原先是「海外三强 / 国产四强」两个分组可切换；按需求国外模型不参与
   * 介绍与比较，国外分组已删除，这里固定只画国产四强。
   * ======================================================= */
  var RADAR_DATA = [
    { name: 'DeepSeek V4-Pro',    value: [4.6, 5.0, 3.0, 5.0, 5.0, 4.6] },
    { name: 'Kimi K3',            value: [4.8, 4.4, 4.2, 5.0, 4.2, 5.0] },
    { name: 'Qwen3.8-Max',        value: [4.5, 4.3, 5.0, 5.0, 4.8, 4.6] },
    { name: 'GLM-5.3',            value: [4.6, 4.6, 3.6, 5.0, 4.4, 4.4] }
  ];
  var RADAR_COLOR = [null, null, '#F59E0B', '#6366F1'];

  /* 雷达图里用的是"产品名"，MODELS 里登记的是"系列名"，做一层映射 */
  var RADAR_ALIAS = {
    'DeepSeek V4-Pro': 'DeepSeek V4',
    'GLM-5.3': '智谱 GLM-5.3'
  };

  def('chart-radar', function (v) {
    var idxMap = window.WB_IDX || {};
    var colors = RADAR_COLOR.map(function (c, i) {
      return c || (i === 0 ? v.accent : v.accent2);
    });
    return radarBase(v, {
      color: colors,
      data: RADAR_DATA.map(function (d) {
        return {
          name: d.name,
          value: d.value,
          idx: idxMap[RADAR_ALIAS[d.name] || d.name]
        };
      })
    });
  });

  function radarBase(v, extra) {
    var mobile = v.mobile;
    return {
      animation: false,
      tooltip: { appendToBody: true,
        backgroundColor: 'rgba(6, 24, 20, .94)',
        borderColor: 'rgba(47, 208, 138, .55)',
        borderWidth: 1,
        textStyle: { color: '#E4F5EC', fontSize: 13 } },
      legend: {
        bottom: 0,
        left: 'center',
        itemWidth: mobile ? 10 : 14,
        itemHeight: mobile ? 10 : 8,
        itemGap: mobile ? 10 : 20,
        textStyle: { color: v.muted, fontSize: mobile ? 10.5 : 12 }
      },
      radar: {
        indicator: [
          { name: mobile ? '编程' : '编程 Coding', max: 5 },
          { name: mobile ? '推理' : '推理 Reasoning', max: 5 },
          { name: '多模态', max: 5 },
          { name: mobile ? '长上下文' : '长上下文', max: 5 },
          { name: '性价比', max: 5 },
          { name: mobile ? 'Agent' : 'Agent 能力', max: 5 }
        ],
        // 窄屏收紧半径并上移中心，给底部图例留空间
        radius: mobile ? '58%' : '62%',
        center: mobile ? ['50%', '42%'] : ['50%', '45%'],
        splitNumber: 4,
        axisName: { color: v.ink, fontSize: mobile ? 10 : 12, fontWeight: 600 },
        splitArea: {
          show: true,
          areaStyle: { color: ['rgba(47, 208, 138, .04)', 'rgba(47, 208, 138, .09)'] }
        },
        splitLine: { lineStyle: { color: 'rgba(47, 208, 138, .22)' } },
        axisLine: { lineStyle: { color: 'rgba(47, 208, 138, .22)' } }
      },
      series: [{
        type: 'radar',
        symbolSize: mobile ? 4 : 6,
        areaStyle: { opacity: 0.18 },
        lineStyle: { width: 2 },
        data: extra.data
      }],
      color: extra.color
    };
  }

  /* ---------------------------------------------------------
   * 原「图 4 · SWE-bench Verified 实测」已于 2026-08-29 移除：
   * 该榜前列绝大多数是国外模型，按需求国外模型不参与介绍与比较，
   * 剔除后只剩 2 根柱子、失去参照意义，因此整节删除（含 models.html 的
   * section 与这里的定义）。若要恢复，需同时补回两处。
   * ------------------------------------------------------- */

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
