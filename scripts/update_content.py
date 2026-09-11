#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模型页 + 智能体应用页 + 百科（Agent Skills / MCP）每日内容更新脚本
================================================================================
用途：为 models.html / wiki-skills.html / wiki-mcp.html 页面的「最新动态」区块追加
      当天检索到的实质变化，并同步更新各页（含 agents.html）页脚的「数据截止」日期。

      （v17 起：agents.html 的「Agent 赛道每日更新」已并入 news.html 动态区
       「智能体动态」模块，由 update_news.py 统一维护；本脚本仅继续为 agents.html
       刷新页脚日期，不再写任何动态块。）

流程：
  1. 从国内可直连媒体源池（量子位 / 爱范儿 / IT之家 / 极客公园）抓取近 N 小时条目，
     按主题 must_kw 初筛（2026-09-09 起弃用 Google News 检索：其链接为
     news.google.com 跳转壳，国内用户无法打开）
  2. 按时间窗过滤 + 与页面已有条目去重
  3. 调 DeepSeek 判断哪些是"实质变化"，并提炼成严格 JSON
  4. Python 侧严格校验（字段白名单 / URL 合法性 / 长度 / HTML 转义）
  5. 由 Python（不是 AI）生成 HTML 并写入标记处

★ 安全铁律（不可违反）★
  - AI 只输出 JSON，绝不生成任何 HTML 标签。所有 HTML 由本脚本渲染。
  - 所有写入页面的文本必须经 html.escape() 转义，杜绝注入。
  - category 必须是白名单内的取值，URL 必须是 http(s) 开头。
  - 本脚本只往「最新动态」标记处追加，以及改页脚日期；
    绝不改动 MODEL_SCORES、AGENTS、价格表、概念长文等主体内容（那些需人工核实）。

用法：
  python scripts/update_content.py                 # 正常跑（需要 DEEPSEEK_API_KEY）
  python scripts/update_content.py --dry-run       # 只打印不写文件
  python scripts/update_content.py --no-ai         # 跳过 AI，用关键词粗筛兜底（无 key 时也能跑）
  python scripts/update_content.py --hours 72      # 自定义时间窗（默认 72 小时）

环境变量：
  DEEPSEEK_API_KEY   DeepSeek API 密钥（GitHub Actions 里从 secrets 注入）。
                    未配置时自动降级为关键词粗筛兜底——仍能产出更新，但质量低于 AI 筛选。
================================================================================
"""

import os
import re
import sys
import json
import html
import argparse
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone

try:
    import feedparser
except ImportError:
    print("需要 feedparser：pip install feedparser")
    sys.exit(1)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CST = timezone(timedelta(hours=8))          # 北京时间
TODAY = datetime.now(CST).strftime("%Y-%m-%d")
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"

# 国内可直连媒体源池（与 update_news.py 同口径；原文链接国内免代理打开）
CN_FEEDS = [
    {"url": "https://www.qbitai.com/feed",   "name": "量子位"},
    {"url": "https://www.ifanr.com/feed",    "name": "爱范儿"},
    {"url": "https://www.ithome.com/rss/",   "name": "IT之家"},
    {"url": "https://www.geekpark.net/rss",  "name": "极客公园"},
]
FEED_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
           "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
FEED_TIMEOUT = 20

# 抓取缓存：多主题共享一次源池抓取
_POOL = {"at": None, "hours": 0, "entries": []}

# ─────────────────────────────────────────────────────────────────────────────
# 主题配置：三组，各自抓什么、写到哪、允许的 category 白名单、CSS 映射
# category 白名单是安全边界 —— AI 只能从中选，选了别的会被校验拦掉
# ─────────────────────────────────────────────────────────────────────────────
TOPICS = [
    {
        "key": "model",
        "label": "国产大模型",
        "page": "models.html",
        "marker": "<!-- __MODEL_DAILY_INSERT__ -->",
        "max_items": 5,
        "categories": ["发布", "调价", "评测"],
        "cat_css": {"发布": "c-model", "调价": "c-event", "评测": "c-paper"},
        # 只关注国产：与模型页"只覆盖国产模型"的口径保持一致
        "queries": [
            "DeepSeek OR 通义千问 OR 智谱GLM OR 豆包 OR 混元 OR Kimi OR MiniMax 发布",
            "国产大模型 发布 OR 开源 OR 升级",
            "大模型 API 降价 OR 调价 OR 涨价",
            "大模型 评测 OR 榜单 OR 跑分",
            # ---- v28 增强：让 AI 更易抓出规格/上下文/开源动态 ----
            "国产大模型 上下文 升级 OR 翻倍 OR 扩展 OR 增强",
            "大模型 上线 OR 接入 OR 降价 限时 OR 活动 OR 促销",
            "国产模型 MIT OR Apache OR 开源协议 OR 开源",
            "国产大模型 新版本 OR X.0 OR 重大更新 OR 升级",
        ],
        "must_kw": ["大模型", "模型", "LLM", "AI", "deepseek", "qwen", "glm",
                    "豆包", "混元", "kimi", "minimax", "文心", "step", "api",
                    "发布", "开源", "降价", "调价", "评测", "榜单"],
    },
    {
        "key": "skills",
        "label": "Agent Skills",
        "page": "wiki-skills.html",
        "marker": "<!-- __SKILLS_DAILY_INSERT__ -->",
        "max_items": 4,
        "categories": ["新技能", "市场", "平台"],
        "cat_css": {"新技能": "c-model", "市场": "c-event", "平台": "c-news"},
        "queries": [
            "Agent Skills OR AI Skill 智能体技能",
            "Claude Skills OR Skill 市场 OR 技能市场",
            "AI Agent 技能 平台 支持 OR 标准",
        ],
        "must_kw": ["skill", "skills", "技能", "agent", "智能体", "claude",
                    "anthropic", "市场", "mcp", "插件", "工具"],
    },
    {
        "key": "mcp",
        "label": "MCP 协议",
        "page": "wiki-mcp.html",
        "marker": "<!-- __MCP_DAILY_INSERT__ -->",
        "max_items": 4,
        "categories": ["协议", "生态", "客户端"],
        "cat_css": {"协议": "c-model", "生态": "c-event", "客户端": "c-news"},
        "queries": [
            "MCP Model Context Protocol 更新 OR 版本",
            "MCP server OR MCP 服务器 生态 OR 目录",
            "MCP 客户端 支持 OR 集成",
        ],
        "must_kw": ["mcp", "model context protocol", "协议", "server", "服务器",
                    "客户端", "client", "生态", "集成", "anthropic"],
    },
    # 注：agent 主题于 v17（2026-09-09）移除——agents.html 的「Agent 赛道每日更新」
    # 已整体并入 news.html 动态区「智能体动态」模块（由 update_news.py 统一维护）。
]

# 页脚「数据截至」的正则（硬事实：只改日期，风险最低）
STAMP_PATTERNS = {
    "models.html": [
        (re.compile(r"(\{\s*v:\s*')[\d-]+(',\s*l:\s*'数据截止')"), r"\g<1>" + TODAY + r"\g<2>"),
    ],
    "wiki-skills.html": [
        (re.compile(r"(数据截至\s*)\d{4}-\d{2}-\d{2}"), r"\g<1>" + TODAY),
    ],
    "wiki-mcp.html": [
        (re.compile(r"(数据截至\s*)\d{4}-\d{2}-\d{2}"), r"\g<1>" + TODAY),
    ],
    "agents.html": [
        (re.compile(r"(数据截至\s*)\d{4}-\d{2}-\d{2}"), r"\g<1>" + TODAY),
    ],
}


# ─────────────────────────────────────────────────────────────────────────────
# v28 数据核对（model-verify）：解析 models.html 数据快照 + DeepSeek 比对
# ─────────────────────────────────────────────────────────────────────────────
# 目标：把「价格 / 规格 / 套餐」三大数据表的当前快照喂给 AI，与当天 AI 新闻比对，
# 找出「疑似变化」写入提醒区。AI 不直接改核心数据 —— 所有数据修改仍走人工。
# 与 model topic 的区别：本区块查的是「疑点」，model topic 查的是「已确认新闻」。
VERIFY_TOPIC = {
    "key": "model-verify",
    "label": "模型页数据核对",
    "page": "models.html",
    "marker": "<!-- __MODEL_VERIFY_INSERT__ -->",
    "max_items": 6,
    "categories": ["价格", "规格", "套餐", "模型阵容"],
    "cat_css": {
        "价格": "c-event",
        "规格": "c-model",
        "套餐": "c-news",
        "模型阵容": "c-paper",
    },
}


def _strip_html(s):
    """剥掉 HTML 标签 + 折叠空白（把表格单元格的 HTML 文本拍平成可读字符串）。"""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s or "")).strip()


def parse_price_table(html_text):
    """解析 models.html 价格表 tbody，返回结构化快照。"""
    m = re.search(r'<tbody[^>]*id="price-tbody"[^>]*>(.*?)</tbody>', html_text, re.DOTALL)
    if not m:
        return []
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", m.group(1), re.DOTALL)
    out = []
    for row in rows:
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL)
        if len(cells) < 6:
            continue
        out.append({
            "model": _strip_html(cells[0]),
            "ctx": _strip_html(cells[1]),
            "in": _strip_html(cells[2]),
            "out": _strip_html(cells[3]),
            "open": _strip_html(cells[4]),
            "note": _strip_html(cells[5]),
        })
    return out


def parse_spec_table(html_text):
    """解析 D 旗舰规格速查 tbody（按 h2 锚点定位）。"""
    m = re.search(r'<h2>📋\s*旗舰规格速查</h2>.*?<tbody>(.*?)</tbody>', html_text, re.DOTALL)
    if not m:
        return []
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", m.group(1), re.DOTALL)
    out = []
    for row in rows:
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL)
        if len(cells) < 7:
            continue
        out.append({
            "model": _strip_html(cells[0]),
            "vendor": _strip_html(cells[1]),
            "date": _strip_html(cells[2]),
            "ctx": _strip_html(cells[3]),
            "modal": _strip_html(cells[4]),
            "strength": _strip_html(cells[5]),
            "weakness": _strip_html(cells[6]),
        })
    return out


def parse_plan_table(html_text):
    """解析 C 订阅套餐 国内服务 tbody（按 h3 锚点定位）。"""
    m = re.search(r'<h3[^>]*>🇨🇳\s*国内服务</h3>.*?<tbody>(.*?)</tbody>', html_text, re.DOTALL)
    if not m:
        return []
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", m.group(1), re.DOTALL)
    out = []
    for row in rows:
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL)
        if len(cells) < 5:
            continue
        out.append({
            "service": _strip_html(cells[0]),
            "plan": _strip_html(cells[1]),
            "monthly": _strip_html(cells[2]),
            "annual": _strip_html(cells[3]),
            "feature": _strip_html(cells[4]),
        })
    return out


def load_snapshot():
    """读取 models.html 三大数据表的当前快照。失败返回空 dict。"""
    path = os.path.join(ROOT, VERIFY_TOPIC["page"])
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except Exception as e:
        print(f"    [跳过] 读取 {path} 失败：{e}")
        return {}
    snap = {
        "prices": parse_price_table(text),
        "specs": parse_spec_table(text),
        "plans": parse_plan_table(text),
    }
    print(f"    快照：价格表 {len(snap['prices'])} 行 · 规格表 {len(snap['specs'])} 行 · 套餐表 {len(snap['plans'])} 行")
    return snap


def _fmt_snapshot_for_prompt(snap):
    """把结构化快照拍平成 AI 可读的纯文本（喂 DeepSeek 用）。"""
    lines = []
    if snap.get("prices"):
        lines.append("【API 按量单价（每百万 token）】")
        for r in snap["prices"]:
            lines.append(f"  - {r['model']} | ctx={r['ctx']} | in={r['in']} | out={r['out']} | 开源={r['open']} | 备注={r['note']}")
    if snap.get("specs"):
        lines.append("\n【旗舰规格速查】")
        for r in snap["specs"]:
            lines.append(f"  - {r['model']} | 厂商={r['vendor']} | 发布={r['date']} | ctx={r['ctx']} | 模态={r['modal']} | 强项={r['strength']} | 短板={r['weakness']}")
    if snap.get("plans"):
        lines.append("\n【订阅套餐（国内服务）】")
        for r in snap["plans"]:
            lines.append(f"  - {r['service']} - {r['plan']} | 月费={r['monthly']} | 年付={r['annual']} | 特点={r['feature']}")
    return "\n".join(lines)


def build_verify_prompt(snap, entries):
    """构造 DeepSeek prompt：让 AI 比对快照 vs 当天新闻，找出疑似变化。"""
    snap_text = _fmt_snapshot_for_prompt(snap)
    listing = "\n".join(
        f"[{i}] 标题：{e['title']}\n    摘要：{e['summary']}\n    链接：{e['url']}\n    来源：{e['source']}"
        for i, e in enumerate(entries)
    )
    return f"""你是「数据核对助手」。下面给出 models.html 模型页当前**三大数据表的快照**（API 价格 / 旗舰规格 / 订阅套餐），以及**当天 AI 新闻候选**。

任务：从候选新闻中找出**与快照中某行直接相关、且可能反映「数据已变」的实质事件**。注意「实质」——只在新闻明确说"X 模型价格改为 Y"、"X 推出新版本"、"X 套餐档位调整"等才算；观点评论、营销、传闻不算。

匹配规则：
- model 字段：必须用快照中已有的模型全名（如"DeepSeek V4-Pro"、"Kimi K3"、"GLM-5.3"、"Qwen3.8-Max"等）。找不到对应的不要硬猜。
- category 必须严格从这四个里选一个：价格 / 规格 / 套餐 / 模型阵容
  - 价格：API 单价调整（输入价/输出价/缓存价/峰谷）
  - 规格：上下文长度、模态、发布日期等规格字段变化
  - 套餐：订阅制月费/年费/额度调整
  - 模型阵容：新增/下线/厂商调整（如「某厂商推出新模型」）
- evidence_i：用候选新闻的编号引用（i 值）
- confidence：high（新闻明确说改了什么）/ medium（暗示/间接证据）/ low（仅有迹象）

只输出严格 JSON，不要任何解释文字，不要 markdown 代码块：
{{"items":[{{"model":"快照中已有模型全名","field":"被影响的字段名（如 input_price/output_price/ctx/date/monthly_fee/plan_name）","current":"快照中当前值","suspect":"疑似已变成什么（不超过40字）","category":"价格|规格|套餐|模型阵容","evidence_i":0,"confidence":"high|medium|low","source":"来源媒体名"}}]}}

规则：
- 最多 {VERIFY_TOPIC['max_items']} 条，按 confidence 排序（high > medium > low）。
- 没有任何疑似变化就输出 {{"items":[]}}。
- 不要编造、不要夸大、不要「宁滥勿缺」——只输出有真实新闻支撑的疑似变化。

当前快照：
{snap_text}

当天新闻候选：
{listing}"""


def ai_verify(snap, entries):
    """调 DeepSeek 比对快照 vs 新闻，返回校验后的 items；失败返回空列表。"""
    if not snap or not any(snap.values()):
        print("    快照为空，跳过 verify")
        return []
    if not entries:
        print("    无候选新闻，跳过 verify")
        return []

    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        print("    未配置 DEEPSEEK_API_KEY → 用关键词兜底（质量低于 AI）")
        return keyword_fallback_verify(snap, entries)

    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [{"role": "user", "content": build_verify_prompt(snap, entries)}],
        "temperature": 0.2,
        "max_tokens": 1500,
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(
        DEEPSEEK_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
    )

    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            body = json.loads(r.read().decode("utf-8"))
        content = body["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"    DeepSeek verify 调用失败：{e}")
        return []

    try:
        data = json.loads(content)
    except Exception:
        m = re.search(r"\{[\s\S]*\}", content)
        if not m:
            print("    verify AI 返回非 JSON，放弃")
            return []
        try:
            data = json.loads(m.group(0))
        except Exception:
            print("    verify AI 返回 JSON 解析失败，放弃")
            return []

    return normalize_verify(data, snap, entries)


def normalize_verify(data, snap, entries):
    """校验 AI 输出：model 必须在快照中存在；category 白名单；confidence 白名单；URL 由 evidence_i 反查。"""
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        print("    verify AI 输出结构不合法")
        return []

    # 构建快照白名单（价格 + 规格 用 model；套餐用 service）
    allowed = set()
    for r in snap.get("prices", []):
        allowed.add(r["model"])
    for r in snap.get("specs", []):
        allowed.add(r["model"])
    for r in snap.get("plans", []):
        allowed.add(r["service"])

    out = []
    for it in data["items"][: VERIFY_TOPIC["max_items"]]:
        if not isinstance(it, dict):
            continue

        model = str(it.get("model", "")).strip()
        if not model or model not in allowed:
            continue

        cat = str(it.get("category", "")).strip()
        if cat not in VERIFY_TOPIC["categories"]:
            continue

        conf = str(it.get("confidence", "")).strip()
        if conf not in ("high", "medium", "low"):
            conf = "low"

        # 用 evidence_i 反查真实 URL（杜绝 AI 编造链接）
        ev_i = it.get("evidence_i")
        url = ""
        if isinstance(ev_i, int) and 0 <= ev_i < len(entries):
            url = entries[ev_i]["url"]

        field = str(it.get("field", "")).strip()[:30]
        current = str(it.get("current", "")).strip()[:60]
        suspect = str(it.get("suspect", "")).strip()[:60]
        if not field or not suspect:
            continue

        out.append({
            "model": model,
            "field": field,
            "current": current,
            "suspect": suspect,
            "category": cat,
            "confidence": conf,
            "url": url,
            "source": str(it.get("source", "")).strip()[:40] or "网络",
        })

    print(f"    verify AI 选出 {len(out)} 条疑似变化（校验后）")
    return out


def keyword_fallback_verify(snap, entries):
    """无 Key 时的兜底：用关键词扫候选新闻，匹配快照模型名 → 粗筛疑似变化。"""
    if not snap or not entries:
        return []
    allowed = set()
    for r in snap.get("prices", []):
        allowed.add(r["model"])
    for r in snap.get("specs", []):
        allowed.add(r["model"])

    out = []
    for e in entries:
        blob = (e["title"] + " " + e["summary"]).lower()
        for m in allowed:
            if m.lower() in blob:
                cat = "价格" if any(k in blob for k in ("降价", "涨价", "调价", "价格")) else \
                      "规格" if any(k in blob for k in ("上下文", "发布", "升级", "上线")) else \
                      "套餐" if any(k in blob for k in ("订阅", "套餐", "月费")) else \
                      "模型阵容"
                out.append({
                    "model": m,
                    "field": "未指定",
                    "current": "见快照",
                    "suspect": e["title"][:60],
                    "category": cat,
                    "confidence": "low",
                    "url": e["url"],
                    "source": e["source"][:40],
                })
                break
        if len(out) >= VERIFY_TOPIC["max_items"]:
            break
    print(f"    verify 关键词兜底选出 {len(out)} 条")
    return out


def render_verify_block(topic, items):
    """渲染「数据核对提醒」HTML（★ AI 不碰 HTML，全由 Python 生成 ★）。"""
    e = html.escape
    conf_label = {"high": "🔴 高", "medium": "🟡 中", "low": "🟢 低"}

    rows = []
    for it in items:
        ev_html = (
            f'<span class="src">来源：<a href="{e(it["url"])}" target="_blank" rel="noopener">{e(it["source"])}</a></span>'
            if it["url"] else '<span class="src">来源：未抓到链接</span>'
        )
        rows.append(
            '        <div class="verify-item">\n'
            f'          <div class="vi-label">{e(it["category"])} · 置信度 {e(conf_label.get(it["confidence"], "🟢 低"))}</div>\n'
            f'          <div class="vi-title">{e(it["model"])} · {e(it["field"])}</div>\n'
            f'          <div class="vi-evidence">当前：{e(it["current"]) or "（无）"}　→　疑似：{e(it["suspect"])}<br>{ev_html}</div>\n'
            '        </div>'
        )

    return (
        '      <div class="verify-day">\n'
        '        <div class="dhead">\n'
        f'          <span class="ddate">{TODAY}</span>\n'
        f'          <span class="dbadge">{len(items)} 条疑似变化</span>\n'
        '        </div>\n'
        + "\n".join(rows) + "\n"
        '      </div>'
    )


def insert_verify_block(topic, block):
    """把 verify 区块写到 marker 之后（最新在最上面）。已写过今天则跳过。"""
    path = os.path.join(ROOT, topic["page"])
    with open(path, encoding="utf-8") as f:
        text = f.read()

    if topic["marker"] not in text:
        print(f"    ✗ {topic['page']} 未找到 verify marker，跳过")
        return False

    if f'class="ddate">{TODAY}</span>' in text:
        print(f"    · {topic['page']} verify 今天已更新过，跳过（幂等）")
        return False

    text = text.replace(topic["marker"], topic["marker"] + "\n" + block, 1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"    ✓ verify 已写入 {topic['page']}")
    return True


def run_verify(args):
    """完整跑一次数据核对：读快照 + 抓新闻 + AI 比对 + 渲染 + 写入。"""
    print(f"[{VERIFY_TOPIC['label']}]")
    snap = load_snapshot()
    if not snap or not any(snap.values()):
        print("    快照为空，跳过\n")
        return False

    model_topic = next((t for t in TOPICS if t["key"] == "model"), None)
    if not model_topic:
        print("    未找到 model topic 配置，跳过\n")
        return False

    entries = fetch_entries(model_topic, args.hours)
    if not entries:
        print("    无候选新闻，跳过\n")
        return False

    if args.no_ai:
        items = keyword_fallback_verify(snap, entries)
    else:
        items = ai_verify(snap, entries)
        if not items:
            print("    verify 未发现疑似变化，本次不写入\n")
            return False

    if not items:
        print("    无合适内容\n")
        return False

    block = render_verify_block(VERIFY_TOPIC, items)
    if args.dry_run:
        print("    --- verify 预览 ---")
        print(block)
        print("    -------------------\n")
        return False

    if insert_verify_block(VERIFY_TOPIC, block):
        return True
    return False


def load_pool(hours):
    """抓国内源池全部条目（近 hours 小时），5 分钟内复用（多主题共享一次抓取）。

    注：update_news.py 早已全量换国内源；本文件抓的是「候选条目池」，随后由
    must_kw 初筛 + DeepSeek/关键词兜底挑出真正的实质变化。
    """
    now = datetime.now(CST)
    if (_POOL["entries"] and _POOL["hours"] == hours and _POOL["at"]
            and (now - _POOL["at"]).total_seconds() < 300):
        return _POOL["entries"]

    cutoff = now - timedelta(hours=hours)
    seen, raw = set(), []
    for fi in CN_FEEDS:
        try:
            req = urllib.request.Request(
                fi["url"],
                headers={"User-Agent": FEED_UA,
                         "Accept": "application/rss+xml, application/xml, text/xml, */*"},
            )
            with urllib.request.urlopen(req, timeout=FEED_TIMEOUT) as r:
                feed = feedparser.parse(r.read().decode("utf-8", "ignore"))
        except Exception as e:
            print(f"    [跳过] 源抓取失败 {fi['name']} → {e}")
            continue

        for e in feed.entries:
            title = (e.get("title") or "").strip()
            link = (e.get("link") or "").strip()
            if not title or not link or link in seen:
                continue

            pub = None
            if getattr(e, "published_parsed", None):
                pub = datetime(*e.published_parsed[:6], tzinfo=timezone.utc).astimezone(CST)
                if pub < cutoff:
                    continue

            summary = re.sub(r"<[^>]+>", "", e.get("summary") or "")[:300].strip()
            seen.add(link)
            raw.append({"title": title, "summary": summary, "url": link,
                        "source": fi["name"], "published": pub})

    _POOL.update(at=now, hours=hours, entries=raw)
    return raw


def fetch_entries(topic, hours):
    """抓该主题候选：国内源池 + must_kw 初筛，按时间倒序最多返回 50 条。"""
    pool = load_pool(hours)
    must = [k.lower() for k in topic["must_kw"]]
    picked = []
    for it in pool:
        blob = (it["title"] + " " + it["summary"]).lower()
        if not any(k in blob for k in must):
            continue
        picked.append(it)
    picked.sort(key=lambda x: x["published"] or datetime.min.replace(tzinfo=CST), reverse=True)
    print(f"    抓到 {len(picked)} 条候选（{hours} 小时内，国内源 + must_kw 初筛）")
    return picked[:50]


# ─────────────────────────────────────────────────────────────────────────────
# 2. AI 判断（DeepSeek）
# ─────────────────────────────────────────────────────────────────────────────
def build_prompt(topic, entries):
    cats = " / ".join(topic["categories"])
    listing = "\n".join(
        f"[{i}] 标题：{e['title']}\n    摘要：{e['summary']}\n    链接：{e['url']}"
        for i, e in enumerate(entries)
    )
    return f"""你是内容更新助手。下面是 RSS 抓取到的候选条目，请挑出真正描述了「{topic['label']}」领域**实质变化**的条目。

要剔除：观点评论、营销软文、重复报道、与主题无关的内容、没有实质信息的空话。
要保留：新版本/新产品发布、官方调价、权威评测结果、生态或平台的重要更新。

category 必须严格从这几个里选一个：{cats}

只输出 JSON，不要任何解释文字，不要 markdown 代码块，格式如下：
{{"items":[{{"i":0,"title":"中文标题，不超过40字","summary":"一句话说明发生了什么变化，不超过80字","category":"{topic['categories'][0]}","source":"来源媒体名"}}]}}

规则：
- "i" 是下面条目的编号，用它引用原条目；"url" 不用你输出，我按编号取原文链接。
- 最多 {topic['max_items']} 条，按重要程度排序。
- 没有符合的就输出 {{"items":[]}}。
- 如实反映原文，不要夸大、不要编造。

候选条目：
{listing}"""


def ai_pick(topic, entries):
    """调 DeepSeek 筛选并提炼。返回校验后的 items，失败返回空列表。"""
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        print("    未配置 DEEPSEEK_API_KEY，跳过 AI 判断")
        return []

    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [{"role": "user", "content": build_prompt(topic, entries)}],
        "temperature": 0.2,
        "max_tokens": 1200,
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(
        DEEPSEEK_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {key}"},
    )

    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            body = json.loads(r.read().decode("utf-8"))
        content = body["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"    DeepSeek 调用失败：{e}")
        return []

    try:
        data = json.loads(content)
    except Exception:
        # 有的模型会在 JSON 外包一层 ```json，兜底剥掉
        m = re.search(r"\{[\s\S]*\}", content)
        if not m:
            print("    AI 返回的不是合法 JSON，放弃")
            return []
        try:
            data = json.loads(m.group(0))
        except Exception:
            print("    AI 返回 JSON 解析失败，放弃")
            return []

    return normalize(data, topic, entries)


# ─────────────────────────────────────────────────────────────────────────────
# 3. 校验（安全边界，全部在此拦下）
# ─────────────────────────────────────────────────────────────────────────────
def normalize(data, topic, entries):
    """把 AI 输出收敛成安全、规范的结构。任何不合规的条目直接丢弃。"""
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        print("    AI 输出结构不合法（缺 items 列表）")
        return []

    out = []
    for it in data["items"][: topic["max_items"]]:
        if not isinstance(it, dict):
            continue

        # 用编号取回真实 URL —— URL 只来自 RSS，AI 无权提供，杜绝编造链接
        idx = it.get("i")
        url = ""
        if isinstance(idx, int) and 0 <= idx < len(entries):
            url = entries[idx]["url"]
        if not url:
            continue

        cat = str(it.get("category", "")).strip()
        if cat not in topic["categories"]:      # 白名单之外的分类一律丢弃
            continue

        title = str(it.get("title", "")).strip()
        summary = str(it.get("summary", "")).strip()
        if not title or len(title) > 60 or not summary or len(summary) > 140:
            continue

        out.append({
            "title": title,
            "summary": summary,
            "category": cat,
            "url": url,
            "source": str(it.get("source", "")).strip()[:40] or "网络",
        })

    print(f"    AI 选出 {len(out)} 条（校验后）")
    return out


def keyword_fallback(topic, entries):
    """无 AI 时的兜底：纯关键词粗筛，取前 N 条。质量低于 AI，但保证流程可跑。"""
    out = []
    for e in entries[: topic["max_items"]]:
        blob = (e["title"] + e["summary"]).lower()
        cat = topic["categories"][0]
        for c, kws in {
            "调价": ["降价", "调价", "涨价", "价格"],
            "评测": ["评测", "榜单", "跑分", "benchmark"],
            "市场": ["市场", "上线", "商店"],
            "平台": ["支持", "集成", "平台"],
            "协议": ["协议", "版本", "规范", "spec"],
            "生态": ["生态", "服务器", "目录", "插件", "商店", "接入"],
            "客户端": ["客户端", "client"],
            "新技能": ["技能", "skill"],
            "发布": ["发布", "上线", "推出", "新版", "更新", "launch", "release"],
            "格局": ["月活", "mau", "用户规模", "份额", "排名", "数据", "整合", "并入"],
            "开源": ["开源", "open source", "opensource", "github", "免费"],
        }.items():
            if c in topic["categories"] and any(k in blob for k in kws):
                cat = c
                break
        out.append({
            "title": e["title"][:60],
            "summary": (e["summary"][:140] or e["title"][:60]),
            "category": cat,
            "url": e["url"],
            "source": e["source"][:40],
        })
    return out


# ─────────────────────────────────────────────────────────────────────────────
# 4. 渲染 HTML（★ 只由 Python 生成，AI 不碰 ★）
# ─────────────────────────────────────────────────────────────────────────────
def render_block(topic, items):
    e = html.escape
    rows = []
    for it in items:
        css = topic["cat_css"].get(it["category"], "c-news")
        rows.append(
            '        <div class="news-item">\n'
            f'          <span class="cat {css}">{e(it["category"])}</span>\n'
            '          <div class="body">\n'
            f'            <h4><a href="{e(it["url"])}" target="_blank" rel="noopener">'
            f'{e(it["title"])}</a></h4>\n'
            f'            <p>{e(it["summary"])}</p>\n'
            f'            <span class="src">来源：<a href="{e(it["url"])}" '
            f'target="_blank" rel="noopener">{e(it["source"])}</a></span>\n'
            '          </div>\n'
            '        </div>'
        )

    return (
        '      <div class="news-day">\n'
        '        <div class="dhead">\n'
        f'          <span class="ddate">{TODAY}</span>\n'
        f'          <span class="dbadge">{len(items)} 条更新</span>\n'
        '        </div>\n'
        + "\n".join(rows) + "\n"
        '      </div>'
    )


def insert_block(topic, block):
    """把区块写到标记之后（新的在最上面）。已写过今天则跳过，保证幂等。"""
    path = os.path.join(ROOT, topic["page"])
    with open(path, encoding="utf-8") as f:
        text = f.read()

    if topic["marker"] not in text:
        print(f"    ✗ {topic['page']} 未找到插入标记，跳过")
        return False

    if f'class="ddate">{TODAY}</span>' in text:
        print(f"    · {topic['page']} 今天已更新过，跳过（幂等）")
        return False

    text = text.replace(topic["marker"], topic["marker"] + "\n" + block, 1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"    ✓ 已写入 {topic['page']}")
    return True


def update_stamp(page):
    """硬事实更新：把页脚「数据截至」刷成今天。只改日期，风险最低。"""
    path = os.path.join(ROOT, page)
    if page not in STAMP_PATTERNS:
        return False
    with open(path, encoding="utf-8") as f:
        text = f.read()
    new = text
    for pat, rep in STAMP_PATTERNS[page]:
        new = pat.sub(rep, new)
    if new == text:
        print(f"    · {page} 页脚日期无变化")
        return False
    with open(path, "w", encoding="utf-8") as f:
        f.write(new)
    print(f"    ✓ {page} 数据截止日期已更新为 {TODAY}")
    return True


# ─────────────────────────────────────────────────────────────────────────────
# main
# ─────────────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="只打印不写文件")
    ap.add_argument("--no-ai", action="store_true", help="跳过 AI，用关键词兜底")
    ap.add_argument("--hours", type=int, default=72, help="RSS 时间窗（小时）")
    args = ap.parse_args()

    print(f"=== 模型页 / 智能体应用页 / 百科每日更新 {TODAY} ===")
    print(f"模式：{'演练（不写文件）' if args.dry_run else '正式写入'}　"
          f"AI：{'关（关键词兜底）' if args.no_ai else '开（DeepSeek）'}\n")

    changed = []
    for topic in TOPICS:
        print(f"[{topic['label']}]")
        entries = fetch_entries(topic, args.hours)
        if not entries:
            print("    无候选条目\n")
            continue

        if args.no_ai:
            items = keyword_fallback(topic, entries)
            print(f"    关键词兜底粗筛 {len(items)} 条（显式 --no-ai，质量低于 AI）")
        else:
            if not os.environ.get("DEEPSEEK_API_KEY"):
                # 无 Key 时不跳过，改用关键词粗筛兜底，保证“每天一搜”始终有产出；
                # 一旦仓库配置了 DEEPSEEK_API_KEY，会自动升级为 AI 高质量筛选。
                print("    未配置 DEEPSEEK_API_KEY → 改用关键词粗筛兜底（质量低于 AI）")
                items = keyword_fallback(topic, entries)
            else:
                items = ai_pick(topic, entries)
                if not items:
                    print("    AI 未选出实质变化，本次不写入\n")
                    continue

        if not items:
            print("    无合适内容\n")
            continue

        block = render_block(topic, items)
        if args.dry_run:
            print("    --- 预览 ---")
            print(block)
            print("    ------------\n")
            continue

        if insert_block(topic, block) or update_stamp(topic["page"]):
            changed.append(topic["page"])
        print()

    # 无论有没有新条目，日期戳都刷一遍（证明今天跑过）
    if not args.dry_run:
        for page in ("models.html", "agents.html", "wiki-skills.html", "wiki-mcp.html"):
            if update_stamp(page) and page not in changed:
                changed.append(page)

    # ---- v28 数据核对（独立流程：读快照 + AI 比对 + 写提醒）----
    # 与 model topic 不同：model 找的是「已确认新闻」，verify 找的是「快照 vs 新闻」的疑点。
    if not args.dry_run:
        if run_verify(args) and VERIFY_TOPIC["page"] not in changed:
            changed.append(VERIFY_TOPIC["page"])
    else:
        run_verify(args)  # dry-run 也跑，输出预览

    print("=== 完成 ===")
    print("变更文件：" + (", ".join(changed) if changed else "无"))
    # 供 Actions 判断是否提交
    with open(os.environ.get("GITHUB_OUTPUT", os.devnull), "a", encoding="utf-8") as f:
        f.write(f"changed={len(changed)}\n")


if __name__ == "__main__":
    main()
