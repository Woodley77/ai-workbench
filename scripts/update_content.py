#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""更新模型、Skills、MCP 动态，以及模型和智能体的每周待核实提醒。

RSS 标题初筛、链接和标题去重后，由 Python 转义并渲染 HTML。
只追加动态区、核对区及动态更新日期，不改模型评分、价格表或概念正文。
始终使用免费规则，不读取 API 密钥、不调用模型接口；--no-ai 保留兼容。
--dry-run 只预览，--hours 控制动态候选时间窗（默认 72 小时）。
每周核对查看至少 168 小时的消息，成功空结果也记录完成，失败保留重试。
"""

import os
import re
import sys
import json
import html
import argparse
import urllib.request
from news_rules import deduplicate
from maintenance import OFFICIAL_FEEDS, safe_url, priority, now_iso, headline_links, record_run, read_json, write_json, seen_records, remember, archive_old_blocks
from pathlib import Path
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

# 国内可直连媒体源池（与 update_news.py 同口径；原文链接国内免代理打开）
CN_FEEDS = [
    {"url": "https://www.qbitai.com/feed",   "name": "量子位"},
    {"url": "https://www.ifanr.com/feed",    "name": "爱范儿"},
    {"url": "https://www.ithome.com/rss/",   "name": "IT之家"},
    {"url": "https://www.geekpark.net/rss",  "name": "极客公园"},
]
FEED_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
           "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
CN_FEEDS += OFFICIAL_FEEDS
FEED_RESULTS = {}
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
    },
    {
        "key": "skills",
        "label": "Agent Skills",
        "page": "wiki-skills.html",
        "marker": "<!-- __SKILLS_DAILY_INSERT__ -->",
        "max_items": 4,
        "categories": ["新技能", "市场", "平台"],
        "cat_css": {"新技能": "c-model", "市场": "c-event", "平台": "c-news"},
    },
    {
        "key": "mcp",
        "label": "MCP 协议",
        "page": "wiki-mcp.html",
        "marker": "<!-- __MCP_DAILY_INSERT__ -->",
        "max_items": 4,
        "categories": ["协议", "生态", "客户端"],
        "cat_css": {"协议": "c-model", "生态": "c-event", "客户端": "c-news"},
    },
    # 注：agent 主题于 v17（2026-09-09）移除——agents.html 的「Agent 赛道每日更新」
    # 已整体并入 news.html 动态区「智能体动态」模块（由 update_news.py 统一维护）。
]

# 页脚「数据截至」的正则（硬事实：只改日期，风险最低）
STAMP_PATTERNS = {
    "models.html": [
        (re.compile(r"(\{\s*v:\s*')[\d-]+(',\s*l:\s*'动态更新日期')"), r"\g<1>" + TODAY + r"\g<2>"),
    ],
    "wiki-skills.html": [
        (re.compile(r"(动态区最近收录\s*)\d{4}-\d{2}-\d{2}"), r"\g<1>" + TODAY),
    ],
    "wiki-mcp.html": [
        (re.compile(r"(动态区最近收录\s*)\d{4}-\d{2}-\d{2}"), r"\g<1>" + TODAY),
    ],
    # 注：agents.html 于 v29 移除自动日期戳 —— 该页数据是「人工核实快照」，
    # 每天刷日期会造成「日期在动、数据没动」的假新鲜。
    # 改为：verify 每天核对 → 发现疑点写提醒 → 人工确认后更新日期与数据。
}


# ─────────────────────────────────────────────────────────────────────────────
# 数据核对（model-verify）：解析页面快照 + 免费规则比对
# ─────────────────────────────────────────────────────────────────────────────
# 目标：把「价格 / 规格 / 套餐」三大数据表的当前快照与新闻比对，
# 找出「疑似变化」写入提醒区；所有核心数据修改仍走人工。
# 与 model topic 的区别：本区块查的是「疑点」，model topic 查的是「已确认新闻」。
VERIFY_TOPICS = [
    {
        "key": "model-verify",
        "label": "模型页数据核对",
        "page": "models.html",
        "marker": "<!-- __MODEL_VERIFY_INSERT__ -->",
        "kind": "model",       # 用哪套快照解析
        "feed_key": "model",   # 复用哪个 TOPICS 的新闻抓取口径
        "max_items": 6,
        "categories": ["价格", "规格", "套餐", "模型阵容"],
        "cat_css": {
            "价格": "c-event",
            "规格": "c-model",
            "套餐": "c-news",
            "模型阵容": "c-paper",
        },
        "scope": "models.html 模型页当前的 **三大数据表快照**（API 价格 / 旗舰规格 / 订阅套餐）",
        "cat_hint": (
            "  - 价格：API 单价调整（输入价/输出价/缓存价/峰谷）\n"
            "  - 规格：上下文长度、模态、发布日期等规格字段变化\n"
            "  - 套餐：订阅制月费/年费/额度调整\n"
            "  - 模型阵容：新增/下线/厂商调整（如「某厂商推出新模型」）"
        ),
        "entity_hint": '必须用快照中已有的模型全名（如 "DeepSeek V4.1 Flash"、"Kimi K3"、"GLM-5.3"、"Qwen3.8-Max" 等）。找不到对应的不要硬猜。',
    },
    {
        "key": "agents-verify",
        "label": "智能体页数据核对",
        "page": "agents.html",
        "marker": "<!-- __AGENTS_VERIFY_INSERT__ -->",
        "kind": "agents",
        "feed_key": "model",
        "max_items": 5,
        "categories": ["榜单", "应用", "规模", "品牌"],
        "cat_css": {
            "榜单": "c-event",
            "应用": "c-model",
            "规模": "c-news",
            "品牌": "c-paper",
        },
        "scope": "agents.html 智能体页当前的 **应用清单快照**（各应用所属厂商、地区、类型与热度标签中的规模数字）",
        "cat_hint": (
            "  - 榜单：排行榜 / 热度名次数据更新\n"
            "  - 应用：新应用发布、功能重大更新、停止服务\n"
            "  - 规模：用户量 / 月活 / Token 消耗等数字更新\n"
            "  - 品牌：厂商品牌整合、改名、并入"
        ),
        "entity_hint": '必须用快照中已有的应用名（如 ChatGPT、Gemini、Claude Code、OpenClaw、豆包、千问办公、Manus 等）。找不到对应的不要硬猜。',
    },
]


def _strip_html(s):
    """剥掉 HTML 标签 + 折叠空白（把表格单元格的 HTML 文本拍平成可读字符串）。"""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s or "")).strip()


def _parse_table(html_text, pattern, fields):
    """按原定位规则提取表格；短行跳过，多余单元格忽略。"""
    match = re.search(pattern, html_text, re.DOTALL)
    if not match:
        return []
    result = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", match.group(1), re.DOTALL):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL)
        if len(cells) >= len(fields):
            result.append({field: _strip_html(cell) for field, cell in zip(fields, cells)})
    return result


def parse_price_table(html_text):
    '解析 models.html 价格表 tbody，返回结构化快照。'
    return _parse_table(html_text, '<tbody[^>]*id="price-tbody"[^>]*>(.*?)</tbody>', ('model', 'ctx', 'in', 'out', 'open', 'note'))


def parse_spec_table(html_text):
    '解析 D 旗舰规格速查 tbody（按 h2 锚点定位）。'
    return _parse_table(html_text, '<h2>📋\\s*旗舰规格速查</h2>.*?<tbody>(.*?)</tbody>', ('model', 'vendor', 'date', 'ctx', 'modal', 'strength', 'weakness'))


def parse_plan_table(html_text):
    '解析 C 订阅套餐 国内服务 tbody（按 h3 锚点定位）。'
    return _parse_table(html_text, '<h3[^>]*>🇨🇳\\s*国内服务</h3>.*?<tbody>(.*?)</tbody>', ('service', 'plan', 'monthly', 'annual', 'feature'))


def parse_agents_snapshot(text):
    """解析 agents.html 的 AGENTS 应用清单（快照）。"""
    m = re.search(r"var AGENTS\s*=\s*\[(.*?)\n\];", text, re.S)
    body = m.group(1) if m else ""
    pat = re.compile(
        r"id:\s*'([^']+)'\s*,\s*name:\s*'([^']+)'\s*,\s*en:\s*'([^']*)'\s*,"
        r"\s*vendor:\s*'([^']*)'\s*,\s*region:\s*'([^']*)'\s*,\s*type:\s*'([^']*)'\s*,"
        r"\s*heat:\s*(\d+)\s*,\s*heatLabel:\s*'([^']*)'",
        re.S,
    )
    out = []
    for b in pat.finditer(body):
        out.append({
            "name": b.group(2),
            "vendor": b.group(4),
            "region": b.group(5),
            "type": b.group(6),
            "heat": int(b.group(7)),
            "heatLabel": b.group(8),
        })
    return out


def load_snapshot(topic):
    """读取该 topic 对应页面的数据快照。失败返回空 dict。"""
    path = os.path.join(ROOT, topic["page"])
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except Exception as e:
        print(f"    [跳过] 读取 {path} 失败：{e}")
        return {}

    if topic.get("kind") == "agents":
        apps = parse_agents_snapshot(text)
        print(f"    快照：应用清单 {len(apps)} 条")
        return {"apps": apps}

    snap = {
        "prices": parse_price_table(text),
        "specs": parse_spec_table(text),
        "plans": parse_plan_table(text),
    }
    print(f"    快照：价格表 {len(snap['prices'])} 行 · 规格表 {len(snap['specs'])} 行 · 套餐表 {len(snap['plans'])} 行")
    return snap


def keyword_fallback_verify(snap, entries, topic):
    """无 Key 时的兜底：用关键词扫候选新闻，匹配快照条目名 → 粗筛疑似变化。"""
    if not snap or not entries:
        return []
    allowed = set()
    for r in snap.get("prices", []):
        allowed.add(r["model"])
    for r in snap.get("specs", []):
        allowed.add(r["model"])
    for r in snap.get("apps", []):
        allowed.add(r["name"])

    is_agents = topic.get("kind") == "agents"
    out = []
    for e in entries:
        blob = (e["title"] + " " + e["summary"]).lower()
        for m in allowed:
            if m.lower() in blob:
                if is_agents:
                    cat = "榜单" if any(k in blob for k in ("榜", "排名", "热度")) else \
                          "规模" if any(k in blob for k in ("月活", "用户", "规模", "token")) else \
                          "品牌" if any(k in blob for k in ("改名", "整合", "并入", "品牌")) else \
                          "应用"
                else:
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
        if len(out) >= topic["max_items"]:
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
            f'          <div class="vi-label">待核实 · {e(it["category"])} · 置信度 {e(conf_label.get(it["confidence"], "🟢 低"))}</div>\n'
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

    if verify_written_today(topic, text):
        print(f"    · {topic['page']} verify 今天已更新过，跳过（幂等）")
        return False

    text = text.replace(topic["marker"], topic["marker"] + "\n" + block, 1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"    ✓ verify 已写入 {topic['page']}")
    return True


def _run_one_verify(topic, args):
    """跑单个页面的数据核对：读快照 + 抓新闻 + 规则比对 + 渲染 + 写入。"""
    print(f"[{topic['label']}]")
    # 非预览模式下，今天已写过提醒就不重复处理。
    if not args.dry_run and verify_written_today(topic):
        print(f"    · {topic['page']} 今天已写过核对条目，跳过（幂等）\n")
        return False
    snap = load_snapshot(topic)
    if not snap or not any(snap.values()):
        raise RuntimeError('页面快照为空，本周核对未完成')

    feed_topic = ({'key': 'agents'} if topic.get('kind') == 'agents' else
                  next((t for t in TOPICS if t["key"] == topic.get("feed_key")), None))
    if not feed_topic:
        print("    未找到 feed topic 配置，跳过\n")
        return False

    entries = fetch_entries(feed_topic, max(args.hours, 168))
    if not entries:
        print("    无候选新闻，跳过\n")
        return False

    items = keyword_fallback_verify(snap, entries, topic)

    if not items:
        print("    无合适内容\n")
        return False

    block = render_verify_block(topic, items)
    if args.dry_run:
        print("    --- verify 预览 ---")
        print(block)
        print("    -------------------\n")
        return False

    return insert_verify_block(topic, block)


def run_verify(args):
    """遍历所有核对主题。返回被改动的页面列表。"""
    changed = []
    state_path = Path(ROOT) / 'data' / 'verify-state.json'
    try:
        state = json.loads(state_path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        state = {}
    week = datetime.now(CST).strftime('%G-W%V')
    for topic in VERIFY_TOPICS:
        if not args.dry_run and state.get(topic['key']) == week:
            print(f"    {topic['label']} 本周已核对，跳过")
            continue
        try:
            if _run_one_verify(topic, args):
                changed.append(topic["page"])
            # 成功且无变化也记入完成；异常保留给下次重试。
            if not args.dry_run:
                state[topic['key']] = week
        except Exception as e:
            print(f"    [错误] {topic['key']} 数据核对失败：{e}\n")
            raise
    if not args.dry_run:
        state_path.parent.mkdir(exist_ok=True)
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return changed


def load_pool(hours):
    """抓国内源池全部条目（近 hours 小时），5 分钟内复用（多主题共享一次抓取）。

    注：update_news.py 早已全量换国内源；本文件抓的是「候选条目池」，随后由
    must_kw 初筛 + 免费关键词规则挑出真正的实质变化。
    """
    now = datetime.now(CST)
    if (_POOL["hours"] == hours and _POOL["at"]
            and (now - _POOL["at"]).total_seconds() < 300):
        return _POOL["entries"]

    cutoff = now - timedelta(hours=hours)
    seen, raw = set(), []
    successful_feeds = 0
    for fi in CN_FEEDS:
        FEED_RESULTS[fi['url']] = {'name':fi['name'],'url':fi['url'],'ok':False}
        try:
            req = urllib.request.Request(
                fi["url"],
                headers={"User-Agent": FEED_UA,
                         "Accept": "application/rss+xml, application/xml, text/xml, */*"},
            )
            with urllib.request.urlopen(req, timeout=FEED_TIMEOUT) as r:
                feed = feedparser.parse(r.read().decode("utf-8", "ignore"))
                if feed.bozo and not feed.entries:
                    raise ValueError('RSS 内容无效')
                successful_feeds += 1
                FEED_RESULTS[fi['url']]['ok'] = True
        except Exception as e:
            print(f"    [跳过] 源抓取失败 {fi['name']} → {e}")
            continue

        for e in feed.entries:
            title = (e.get("title") or "").strip()
            link = (e.get("link") or "").strip()
            if not title or not safe_url(link) or link in seen:
                continue

            pub = None
            parsed_date = getattr(e,"published_parsed",None) or getattr(e,"updated_parsed",None)
            if parsed_date:
                pub = datetime(*parsed_date[:6], tzinfo=timezone.utc).astimezone(CST)
                if pub < cutoff:
                    continue

            summary = re.sub(r"<[^>]+>", "", e.get("summary") or "")[:300].strip()
            seen.add(link)
            raw.append({"title": title, "summary": summary, "url": link,
                        "source": fi["name"], "published": pub, "official": bool(fi.get("official"))})

    print(f"    RSS 成功 {successful_feeds}/{len(CN_FEEDS)} 个")
    if not successful_feeds:
        raise RuntimeError('全部主题 RSS 源失败，不能认定为没有变化')
    raw.sort(key=priority, reverse=True)
    raw = deduplicate(raw)
    _POOL.update(at=now, hours=hours, entries=raw)
    return raw


def fetch_entries(topic, hours):
    """抓该主题候选：按标题里的主题主体筛选，按时间倒序最多返回 50 条。"""
    pool = load_pool(hours)
    picked = []
    for it in pool:
        if not topic_relevant(topic, it):
            continue
        picked.append(it)
    picked.sort(key=priority, reverse=True)
    print(f"    抓到 {len(picked)} 条候选（{hours} 小时内，标题主题筛选）")
    return picked[:50]


def topic_relevant(topic, entry):
    """在 AI 前后都使用的保守主题门槛，避免摘要里的泛词造成串区。"""
    title = entry['title'].lower()
    key = topic['key']
    if key == 'agents':
        return bool(re.search(r'agent|智能体|助手|chatgpt|gemini|claude|codex|manus|豆包|千问|办公|openclaw|trae', title)) and bool(
            re.search(r'发布|上线|更新|功能|用户|月活|规模|排名|榜单|改名|整合|并入|停服|停止|品牌', title))
    if key == 'mcp':
        return bool(re.search(r'(?<![a-z])mcp(?![a-z])|model context protocol', title))
    if key == 'skills':
        return bool(re.search(r'(?<![a-z])skills?(?![a-z])|技能', title)) and bool(
            re.search(r'agent|智能体|claude|anthropic|codex|openai|插件|技能市场|skills?', title))
    if key == 'model':
        if re.search(r'负责人|离职|接棒|人事|高管|管理层|编程语言|汽车模型|车模', title):
            return False
        vendor = re.search(r'deepseek|qwen|通义|千问|智谱|glm|豆包|混元|kimi|minimax|文心|百川|阶跃|stepfun|mimo|小米|国产大模型', title)
        change = re.search(r'模型|发布|推出|上线|升级|更新|开源|价格|调价|降价|涨价|评测|跑分|榜单|api|上下文|推理', title)
        return bool(vendor and change)
    return False


# ─────────────────────────────────────────────────────────────────────────────
# 2. 免费关键词筛选
# ─────────────────────────────────────────────────────────────────────────────


def keyword_fallback(topic, entries):
    """免费关键词粗筛，取前 N 条；相关性由 fetch_entries 先检查。"""
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


def _read_page(page):
    """读页面文本；失败返回 None。"""
    try:
        with open(os.path.join(ROOT, page), encoding="utf-8") as f:
            return f.read()
    except Exception:
        return None


def page_written_today(topic, text=None):
    """只读判断：该 topic 的页面今天是否已写过块（与 insert_block 的幂等口径一致）。

    用途：已写过就直接跳过，避免同一日期重复写入。判重粒度是
      「整天」（不像 update_news 按早晚时段分），CI 每天 4 班 → 每个主题一天白调 3 次，
      结果全被幂等丢弃。2026-09-24 改为前置判重，兜底能力不变（当天首班仍正常调 AI）。
    """
    if text is None:
        text = _read_page(topic["page"])
    if text is None:
        return False
    idx = text.find(topic['marker'])
    if idx < 0:
        return False
    section = text[idx:]
    end = section.find('</section>')
    if end >= 0:
        section = section[:end]
    return f'class="ddate">{TODAY}</span>' in section


def verify_written_today(topic, text=None):
    """只读判断：该页的 **verify 区段**今天是否已写过核对条目。

    ⚠️ verify 绝不能用整页 `class="ddate">{TODAY}` 判重：同页的「最新动态」块也用同一个
    ddate 渲染，而 main() 里 TOPICS 循环**先于** run_verify 执行 → 动态块一写进去，
    verify 就被误判成「今天已更新过」，此后永远写不进去。
    这正是 v28~v29 期间 model-verify **一次都没成功写入过** 的原因（agents.html 不在
    TOPICS 里、没有动态块，所以只有 agents-verify 能正常写入）。
    现在把判重范围限定为 marker 之后的那个滚动框（到最近的 </div> 为止）。
    """
    if text is None:
        text = _read_page(topic["page"])
    if text is None:
        return False
    idx = text.find(topic["marker"])
    if idx == -1:
        return False
    tail = text[idx:]
    end = tail.find("</div>")
    if end != -1:
        tail = tail[:end]
    return f'class="ddate">{TODAY}</span>' in tail


def insert_block(topic, block):
    """把已筛出的新链接写到标记之后，补班用独立的时间标签。"""
    path = os.path.join(ROOT, topic["page"])
    with open(path, encoding="utf-8") as f:
        text = f.read()

    if topic["marker"] not in text:
        print(f"    ✗ {topic['page']} 未找到插入标记，跳过")
        return False

    if page_written_today(topic, text):
        supplemental = f"{TODAY} 补充 {datetime.now(CST):%H:%M}"
        block = block.replace(f'class="ddate">{TODAY}</span>',
                              f'class="ddate">{supplemental}</span>', 1)

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
def _main_inner():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="只打印不写文件")
    ap.add_argument("--no-ai", action="store_true", help="跳过 AI，用关键词兜底")
    ap.add_argument("--hours", type=int, default=72, help="RSS 时间窗（小时）")
    args = ap.parse_args()
    print(f"=== 模型页 / 智能体应用页 / 百科每日更新 {TODAY} ===")
    print(f"模式：{'演练（不写文件）' if args.dry_run else '正式写入'}　"
          "筛选：免费关键词规则（不支持付费 API）\n")

    FEED_RESULTS.clear()
    changed = []
    state_path = Path(ROOT) / 'data' / 'content-seen.json'
    try:
        seen_by_topic = json.loads(state_path.read_text(encoding='utf-8'))
    except (OSError, ValueError, TypeError):
        seen_by_topic = {}
    for topic in TOPICS:
        print(f"[{topic['label']}]")
        entries = fetch_entries(topic, args.hours)
        page_text = _read_page(topic['page']) or ''
        existing = set(re.findall(r'<h4><a href="([^"]+)"', page_text))
        records = seen_records(seen_by_topic.get(topic['key'], {}))
        old_seen = set(records)
        fresh = [e for e in entries if e['url'] not in old_seen and e['url'] not in existing]
        history = [html.unescape(re.sub(r'<[^>]+>', '', title)) for title in
                   re.findall(r'<h4><a[^>]*>(.*?)</a>', page_text, re.DOTALL)]
        fresh = deduplicate(fresh, history)
        entries = fresh
        if not entries:
            print("    无新候选，跳过\n")
            continue

        items = keyword_fallback(topic, entries)
        print(f"    免费关键词筛选 {len(items)} 条")

        if not items:
            if not args.dry_run:
                seen_by_topic[topic['key']] = remember(records, [e['url'] for e in entries])
            print("    无合适内容\n")
            continue

        block = render_block(topic, items)
        if args.dry_run:
            print("    --- 预览 ---")
            print(block)
            print("    ------------\n")
            continue

        if insert_block(topic, block):
            changed.append(topic["page"])
            update_stamp(topic['page'])
            seen_by_topic[topic['key']] = remember(records, [e['url'] for e in entries])
        print()

    if not args.dry_run:
        state_path.parent.mkdir(exist_ok=True)
        write_json(state_path, seen_by_topic)

    # ---- v28 数据核对（独立流程：读快照 + 规则比对 + 写提醒）----
    # 与 model topic 不同：model 找的是「已确认新闻」，verify 找的是「快照 vs 新闻」的疑点。
    for page in run_verify(args):
        if not args.dry_run and page not in changed:
            changed.append(page)

    print("=== 完成 ===")
    print("变更文件：" + (", ".join(changed) if changed else "无"))
    # 供 Actions 判断是否提交
    with open(os.environ.get("GITHUB_OUTPUT", os.devnull), "a", encoding="utf-8") as f:
        f.write(f"changed={len(changed)}\n")


def main():
    before = headline_links(ROOT)
    started = now_iso()
    dry_run = '--dry-run' in sys.argv
    try:
        _main_inner()
        if not dry_run:
            archive_old_blocks(ROOT)
    except Exception:
        if not dry_run: record_run(ROOT,'content',started,FEED_RESULTS,before,error=True)
        raise
    if not dry_run: record_run(ROOT,'content',started,FEED_RESULTS,before)


if __name__ == "__main__":
    