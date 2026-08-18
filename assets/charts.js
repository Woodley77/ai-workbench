/* 模型对比页 · 图表脚本 */
(function () {
  'use strict';

  var style = getComputedStyle(document.documentElement);
  var accent = style.getPropertyValue('--accent').trim();
  var accent2 = style.getPropertyValue('--accent2').trim();
  var ink = style.getPropertyValue('--ink').trim();
  var muted = style.getPropertyValue('--muted').trim();
  var rule = style.getPropertyValue('--rule').trim();
  var bg2 = style.getPropertyValue('--bg2').trim();

  var palette = [accent, accent2, '#F59E0B', '#22A5F7'];

  function mk(elId, option) {
    var el = document.getElementById(elId);
    if (!el) return;
    var chart = echarts.init(el, null, { renderer: 'svg' });
    chart.setOption(option);
    window.addEventListener('resize', function () { chart.resize(); });
  }

  var radarCommon = {
    animation: false,
    tooltip: { appendToBody: true },
    legend: {
      bottom: 0,
      textStyle: { color: muted, fontSize: 12 },
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
      axisName: { color: muted, fontSize: 12 },
      splitArea: { show: false },
      splitLine: { lineStyle: { color: rule } },
      axisLine: { lineStyle: { color: rule } }
    },
    series: [{
      type: 'radar',
      symbolSize: 4,
      data: []
    }]
  };

  /* 图 1 · 海外三强 */
  mk('chart-overseas', Object.assign({}, radarCommon, {
    color: palette,
    series: [Object.assign({}, radarCommon.series[0], {
      data: [
        { name: 'GPT-5.6 Sol', value: [5.0, 4.5, 4.2, 4.5, 3.8, 5.0] },
        { name: 'Claude Fable 5', value: [4.9, 4.8, 4.0, 4.8, 3.2, 4.8] },
        { name: 'Gemini 3.5 Flash', value: [4.3, 4.0, 5.0, 5.0, 4.6, 4.5] }
      ]
    })]
  }));

  /* 图 2 · 国产四强 */
  mk('chart-domestic', Object.assign({}, radarCommon, {
    color: [accent, accent2, '#F59E0B', '#6366F1'],
    series: [Object.assign({}, radarCommon.series[0], {
      data: [
        { name: 'DeepSeek V4-Pro', value: [4.6, 5.0, 3.0, 5.0, 5.0, 4.6] },
        { name: 'Kimi K3', value: [4.8, 4.4, 4.2, 5.0, 4.2, 5.0] },
        { name: 'Qwen3.8-Max', value: [4.5, 4.3, 5.0, 5.0, 4.8, 4.6] },
        { name: 'GLM-5.3', value: [4.6, 4.6, 3.6, 5.0, 4.4, 4.4] }
      ]
    })]
  }));

  /* 图 3 · SWE-bench Verified 横向柱状 */
  var swe = [
    { name: 'Claude Fable 5', value: 95.0 },
    { name: 'Claude Opus 4.8', value: 88.6 },
    { name: 'Gemini 3.1 Pro', value: 80.6 },
    { name: 'DeepSeek V4-Pro', value: 80.6 },
    { name: 'MiniMax M2.7', value: 80.2 },
    { name: 'Claude Sonnet 4.6', value: 79.6 }
  ];

  mk('chart-swebench', {
    animation: false,
    tooltip: {
      appendToBody: true,
      valueFormatter: function (v) { return v + '%'; }
    },
    grid: { left: 130, right: 40, top: 20, bottom: 30 },
    xAxis: {
      type: 'value',
      max: 100,
      axisLabel: { color: muted, formatter: '{value}%' },
      splitLine: { lineStyle: { color: rule } }
    },
    yAxis: {
      type: 'category',
      data: swe.map(function (d) { return d.name; }).reverse(),
      axisLabel: { color: ink, fontSize: 12 },
      axisLine: { lineStyle: { color: rule } },
      axisTick: { show: false }
    },
    series: [{
      type: 'bar',
      data: swe.map(function (d) { return d.value; }).reverse(),
      barWidth: 18,
      itemStyle: {
        borderRadius: [0, 6, 6, 0],
        color: function (p) { return p.dataIndex === swe.length - 1 ? accent : accent2; }
      },
      label: {
        show: true,
        position: 'right',
        formatter: function (p) { return p.value + '%'; },
        color: muted,
        fontSize: 12
      }
    }]
  });
})();
