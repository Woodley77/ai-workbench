#!/usr/bin/env python3
"""Daily AI news updater - fetches RSS feeds and inserts into news.html."""

import feedparser
import html
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ── RSS sources ──────────────────────────────────────────────
FEEDS = [
    {"url": "https://news.ycombinator.com/rss",            "name": "Hacker News"},
    {"url": "http://export.arxiv.org/rss/cs.AI",           "name": "arXiv cs.AI"},
    {"url": "http://export.arxiv.org/rss/cs.CL",           "name": "arXiv cs.CL"},
    {"url": "https://techcrunch.com/feed/",                 "name": "TechCrunch"},
    {"url": "https://www.jiqizhixin.com/rss",              "name": "机器之心"},
    {"url": "https://36kr.com/feed",                        "name": "36Kr"},
]

# ── AI relevance keywords ────────────────────────────────────
AI_KEYWORDS = [
    "ai", "a.i.", "artificial intelligence", "machine learning", "ml",
    "llm", "large language model", "gpt", "chatgpt", "claude", "gemini",
    "llama", "mistral", "deepseek", "qwen", "openai", "anthropic",
    "generative", "transformer", "neural", "diffusion", "rag",
    "agent", "multimodal", "embedding", "fine-tun", "prompt",
    "人工智能", "大模型", "大语言模型", "机器学习", "深度学习",
    "智能体", "多模态", "生成式", "开源模型", "算力", "推理",
]

# ── Classification keywords ──────────────────────────────────
MODEL_KW = ["gpt", "chatgpt", "claude", "gemini", "llama", "mistral",
            "deepseek", "qwen", "kimi", "glm", "文心", "豆包", "minimax",
            "混元", "step-", "flux", "stable diffusion", "veo", "kling",
            "seedance", "vidu", "midjourney", "sora", "model", "模型",
            "开源", "open-source", "open source", "release", "发布",
            "benchmark", "评测", "swebench", "mmlu", "elo"]

PAPER_KW = ["paper", "arxiv", "research", "study", "论文", "研究",
            "analysis", "survey", "experiment"]

INDUSTRY_KW = ["funding", "融资", "收购", "acquisition", "ipo", "上市",
               "partnership", "合作", "投资", "investment", "估值",
               "valuation", "launch", "推出", "shut down", "关停",
               "rebrand", "改名"]


def classify(title: str) -> str:
    t = title.lower()
    for kw in MODEL_KW:
        if kw in t:
            return "模型"
    for kw in PAPER_KW:
        if kw in t:
            return "论文"
    for kw in INDUSTRY_KW:
        if kw in t:
            return "行业"
    return "热点"


def is_ai_related(title: str, summary: str = "") -> bool:
    text = (title + " " + summary).lower()
    return any(kw in text for kw in AI_KEYWORDS)


def clean_summary(text: str, limit: int = 180) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text).strip()
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0] + "…"
    return text


def fetch_news():
    """Fetch and filter news from all RSS feeds."""
    items = []
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=36)

    for feed_info in FEEDS:
        try:
            feed = feedparser.parse(feed_info["url"])
            if feed.bozo and not feed.entries:
                print(f"  [warn] feed error: {feed_info['name']}")
                continue
            for entry in feed.entries:
                published = None
                for attr in ("published_parsed", "updated_parsed"):
                    if hasattr(entry, attr) and getattr(entry, attr):
                        try:
                            published = datetime(*getattr(entry, attr)[:6],
                                                 tzinfo=timezone.utc)
                        except Exception:
                            pass
                        break
                if published is None:
                    published = now  # fallback if no date

                if published < cutoff:
                    continue

                title = entry.get("title", "").strip()
                link = entry.get("link", "").strip()
                summary = entry.get("summary", "")
                if not title or not link:
                    continue
                if not is_ai_related(title, summary):
                    continue

                items.append({
                    "title": title,
                    "link": link,
                    "summary": clean_summary(summary),
                    "source": feed_info["name"],
                    "published": published,
                    "category": classify(title),
                })
        except Exception as e:
            print(f"  [error] {feed_info['name']}: {e}")

    items.sort(key=lambda x: x["published"], reverse=True)

    # Diversify: pick up to 2 per category, then fill
    selected = []
    for cat in ("模型", "热点", "行业", "论文"):
        cat_items = [i for i in items if i["category"] == cat and i not in selected]
        selected.extend(cat_items[:2])
    for item in items:
        if len(selected) >= 8:
            break
        if item not in selected:
            selected.append(item)
    return selected[:8]


def generate_block(items, date_str):
    """Generate an HTML news-day block."""
    badge_colors = {
        "模型": "#7C3AED",
        "热点": "#F59E0B",
        "行业": "#22A5F7",
        "论文": "#10B981",
    }
    lines = [
        '    <div class="news-day">',
        f'      <h3 class="news-date">{date_str}</h3>',
    ]
    for item in items:
        color = badge_colors.get(item["category"], "#7C3AED")
        lines.extend([
            '      <div class="news-item">',
            f'        <span class="news-badge" style="background:{color}">{item["category"]}</span>',
            '        <div class="news-body">',
            f'          <a class="news-title" href="{item["link"]}" target="_blank" rel="noopener">{html.escape(item["title"])}</a>',
            f'          <p class="news-summary">{html.escape(item["summary"])}</p>',
            f'          <span class="news-source">{item["source"]}</span>',
            '        </div>',
            '      </div>',
        ])
    lines.append("    </div>")
    return "\n".join(lines)


def update_news_html(block):
    """Insert block after __DAILY_INSERT__ marker."""
    path = Path("news.html")
    content = path.read_text(encoding="utf-8")
    marker = "<!-- __DAILY_INSERT__"
    if marker not in content:
        print("ERROR: marker not found")
        return False

    lines = content.split("\n")
    out = []
    inserted = False
    for line in lines:
        out.append(line)
        if marker in line and not inserted:
            out.append(block)
            inserted = True

    if not inserted:
        return False
    path.write_text("\n".join(out), encoding="utf-8")
    return True


def main():
    beijing_tz = timezone(timedelta(hours=8))
    now_bj = datetime.now(beijing_tz)
    date_str = now_bj.strftime("%Y-%m-%d")

    # Skip if today's entry already exists
    news_path = Path("news.html")
    content = news_path.read_text(encoding="utf-8")
    if f'class="news-date">{date_str}<' in content:
        print(f"News for {date_str} already exists, skipping.")
        return

    print(f"Fetching AI news for {date_str}...")
    items = fetch_news()
    if not items:
        print("No AI news found today, skipping.")
        return

    print(f"Found {len(items)} relevant items")
    block = generate_block(items, date_str)
    if update_news_html(block):
        print(f"✓ news.html updated for {date_str}")
    else:
        print("✗ Failed to update news.html")


if __name__ == "__main__":
    main()
