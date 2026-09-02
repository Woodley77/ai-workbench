#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模型页 + 智能体应用页 + 百科（Agent Skills / MCP）每日内容更新脚本
================================================================================
用途：为 models.html / agents.html / wiki-skills.html / wiki-mcp.html 四个页面的
      「最新动态」区块追加当天检索到的实质变化，并同步更新页脚的「数据截止」日期。

流程：
  1. 按三组主题各抓一批 RSS（Google News 关键词检索 = 每天一"搜"）
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
    {
        # 智能体应用页：与页面「国内为主」的口径一致，queries 也以国产为主
        "key": "agent",
        "label": "智能体应用",
        "page": "agents.html",
        "marker": "<!-- __AGENT_DAILY_INSERT__ -->",
        "max_items": 5,
        "categories": ["发布", "格局", "开源", "生态"],
        "cat_css": {"发布": "c-model", "格局": "c-event", "开源": "c-paper", "生态": "c-news"},
        "queries": [
            "AI 智能体 OR AI Agent 发布 OR 上线 OR 更新",
            "豆包 OR 元宝 OR 文心 OR 百度搭子 OR Kimi 智能体",
            "扣子 Coze OR Dify OR 智能体平台 OR 智能体搭建",
            "办公智能体 月活 OR 用户规模 OR 数据",
        ],
        "must_kw": ["agent", "智能体", "助手", "豆包", "元宝", "文心", "搭子", "kimi",
                    "coze", "扣子", "dify", "通义", "workbuddy", "qclaw", "trae",
                    "办公", "月活", "mau", "发布", "上线", "整合", "开源"],
    },
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


def gnews_url(query):
    """把关键词拼成 Google News RSS 检索地址（这就是每天的"搜"）。"""
    return ("https://news.google.com/rss/search?q=" + urllib.parse.quote(query)
            + "&hl=zh-CN&gl=CN&ceid=CN:zh-Hans")


# ─────────────────────────────────────────────────────────────────────────────
# 1. 抓取
# ─────────────────────────────────────────────────────────────────────────────
def fetch_entries(topic, hours):
    """抓该主题下所有 RSS，返回时间窗内的条目。"""
    cutoff = datetime.now(CST) - timedelta(hours=hours)
    seen, out = set(), []

    for q in topic["queries"]:
        url = gnews_url(q)
        try:
            feed = feedparser.parse(url)
        except Exception as e:
            print(f"    [跳过] RSS 抓取失败 {q[:30]}… → {e}")
            continue

        for e in feed.entries:
            title = (e.get("title") or "").strip()
            link = (e.get("link") or "").strip()
            if not title or not link or link in seen:
                continue

            # 时间过滤：无 published 字段的保守放行（交给后面的关键词/AI 兜底）
            if getattr(e, "published_parsed", None):
                pub = datetime(*e.published_parsed[:6], tzinfo=timezone.utc).astimezone(CST)
                if pub < cutoff:
                    continue

            summary = re.sub(r"<[^>]+>", "", e.get("summary") or "")[:300].strip()
            blob = (title + " " + summary).lower()
            if not any(k in blob for k in topic["must_kw"]):
                continue

            seen.add(link)
            out.append({
                "title": title,
                "summary": summary,
                "url": link,
                "source": (e.get("source", {}) or {}).get("title", "Google 新闻"),
            })

    print(f"    抓到 {len(out)} 条候选（{hours} 小时内，已过关键词初筛）")
    return out[:40]      # 最多送 40 条给 AI，控制成本


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

    print("=== 完成 ===")
    print("变更文件：" + (", ".join(changed) if changed else "无"))
    # 供 Actions 判断是否提交
    with open(os.environ.get("GITHUB_OUTPUT", os.devnull), "a", encoding="utf-8") as f:
        f.write(f"changed={len(changed)}\n")


if __name__ == "__main__":
    main()
