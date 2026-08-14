#!/usr/bin/env python3
"""
AI 新闻自动更新脚本 —— 抓取 RSS 源并插入 news.html。

══════════════════════════════════════════════════════════════
中文优先规则（必须遵守）
══════════════════════════════════════════════════════════════
1. 所有新闻标题和摘要必须为中文
2. 仅以下内容允许保留英文：
   - 模型名称（如 GPT-5.6、Claude Opus 5、DeepSeek V4）
   - 公司名（如 OpenAI、Anthropic、NVIDIA）
   - 技术术语（如 MoE、RAG、tokens/s、API）
   - 基准测试名（如 SWE-bench、HLE、MMLU）
3. 英文新闻必须翻译标题和摘要为中文后才能发布
4. 中文 RSS 源优先抓取，英文源仅作补充
5. 若英文新闻无法翻译，则跳过该条新闻
══════════════════════════════════════════════════════════════
"""

import feedparser
import html
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ── RSS 源（中文优先，英文仅补充）──────────────────────────────
FEEDS = [
    # 中文源（优先抓取，国际可访问）
    {"url": "https://news.google.com/rss/search?q=AI+大模型+OR+人工智能+OR+大语言模型&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
     "name": "Google 新闻·AI", "lang": "zh"},
    {"url": "https://news.google.com/rss/search?q=DeepSeek+OR+通义千问+OR+智谱+OR+字节+AI&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
     "name": "Google 新闻·国产模型", "lang": "zh"},
    {"url": "https://news.google.com/rss/search?q=OpenAI+OR+Anthropic+OR+Gemini+OR+Claude&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
     "name": "Google 新闻·海外模型", "lang": "zh"},
    {"url": "https://tech.ifeng.com/c/ai/rss", "name": "凤凰科技·AI", "lang": "zh"},
    # 英文源（仅补充，需翻译）
    {"url": "https://news.ycombinator.com/rss", "name": "Hacker News", "lang": "en"},
    {"url": "https://techcrunch.com/feed/", "name": "TechCrunch", "lang": "en"},
]

# ── AI 相关关键词 ────────────────────────────────────────────
AI_KEYWORDS = [
    "ai", "a.i.", "artificial intelligence", "machine learning", "ml",
    "llm", "large language model", "gpt", "chatgpt", "claude", "gemini",
    "llama", "mistral", "deepseek", "qwen", "openai", "anthropic",
    "generative", "transformer", "neural", "diffusion", "rag",
    "agent", "multimodal", "embedding", "fine-tun", "prompt",
    "人工智能", "大模型", "大语言模型", "机器学习", "深度学习",
    "智能体", "多模态", "生成式", "开源模型", "算力", "推理",
    "芯片", "训练", "微调", "向量", "检索增强",
]

# ── 分类关键词 ───────────────────────────────────────────────
MODEL_KW = ["gpt", "chatgpt", "claude", "gemini", "llama", "mistral",
            "deepseek", "qwen", "kimi", "glm", "文心", "豆包", "minimax",
            "混元", "step-", "flux", "stable diffusion", "veo", "kling",
            "seedance", "vidu", "midjourney", "sora", "model", "模型",
            "开源", "open-source", "open source", "release", "发布",
            "benchmark", "评测", "swebench", "mmlu", "elo", "权重",
            "参数", "moE", "moe", "推理", "tokens/s", "ultrafast"]

PAPER_KW = ["paper", "arxiv", "research", "study", "论文", "研究",
            "analysis", "survey", "experiment", "基准", "benchmark"]

INDUSTRY_KW = ["funding", "融资", "收购", "acquisition", "ipo", "上市",
               "partnership", "合作", "投资", "investment", "估值",
               "valuation", "launch", "推出", "shut down", "关停",
               "rebrand", "改名", "价格", "涨价", "降价", "api", "开源"]

# ── 国内企业/产品关键词（用于区分国内外）─────────────────────────
DOMESTIC_KW = [
    "deepseek", "qwen", "通义千问", "阿里", "alibaba", "智谱", "glm", "z.ai",
    "字节", "bytedance", "豆包", "doubao", "腾讯", "tencent", "混元", "hunyuan",
    "华为", "huawei", "昇腾", "ascend", "商汤", "sensetime", "sensenova",
    "百度", "baidu", "文心", "ernie", "kimi", "月之暗面", "moonshot",
    "minimax", "美团", "meituan", "京东", "jd.com",
    "字节跳动", "veGiantModel", "seedrealtime", "welM", "华为昇腾",
    "杭州", "浙江", "深圳", "北京", "上海", "国产", "国内",
]


def contains_chinese(text: str) -> bool:
    """检查文本是否包含中文字符。"""
    return bool(re.search(r'[\u4e00-\u9fff]', text))


def classify(title: str) -> str:
    """根据标题关键词分类新闻。"""
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


# 分类标签 → CSS 类名映射
CAT_CSS = {
    "模型": "c-model",
    "热点": "c-news",
    "行业": "c-event",
    "论文": "c-paper",
}


def is_domestic(title: str, summary: str = "") -> bool:
    """判断新闻是否为国内新闻（中国企业和产品相关）。"""
    text = (title + " " + summary).lower()
    return any(kw in text for kw in DOMESTIC_KW)


def is_ai_related(title: str, summary: str = "") -> bool:
    """判断新闻是否与 AI 相关。"""
    text = (title + " " + summary).lower()
    return any(kw in text for kw in AI_KEYWORDS)


def clean_summary(text: str, limit: int = 180) -> str:
    """清理 HTML 标签并截断摘要。"""
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text).strip()
    # 移除 Google News 前缀
    text = re.sub(r'^[^-]+-\s*', '', text)
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0] + "…"
    return text


def clean_title(title: str) -> str:
    """清理标题，移除 Google News 等来源前缀。"""
    # 移除 " - 来源名" 后缀
    title = re.sub(r'\s*-\s*[^-]+$', '', title)
    # 移除开头的来源标记
    title = re.sub(r'^\[.*?\]\s*', '', title)
    return title.strip()


# ── 英文→中文翻译映射表（关键词级）──────────────────────────────
TRANSLATIONS = {
    # 动作类
    "introduces": "推出", "launches": "发布", "unveils": "发布", "announces": "宣布",
    "releases": "发布", "debuts": "首发", "rolls out": "推出", "rolls out":
    "推出", "debuts": "首发", "updates": "更新", "upgrades": "升级",
    "open sources": "开源", "open-source": "开源", "open source": "开源",
    "raises": "融资", "funding": "融资", "acquires": "收购",
    "partners with": "合作", "teams up with": "合作",
    "shuts down": "关停", "discontinues": "停用",
    "says": "表示", "reports": "报告", "claims": "声称",
    "beats": "超越", "surpasses": "超越", "outperforms": "性能超越",
    # 产品类
    "new ai model": "新 AI 模型", "ai model": "AI 模型",
    "language model": "语言模型", "large language model": "大语言模型",
    "ai agent": "AI 智能体", "agent": "智能体",
    "chatbot": "聊天机器人", "assistant": "助手",
    # 技术类
    "artificial intelligence": "人工智能", "machine learning": "机器学习",
    "deep learning": "深度学习", "neural network": "神经网络",
    "generative ai": "生成式 AI", "multimodal": "多模态",
    "inference": "推理", "training": "训练", "fine-tuning": "微调",
    "open source": "开源", "benchmark": "基准测试",
    "context window": "上下文窗口", "token": "token",
    "parameters": "参数", "weights": "权重",
    # 行业类
    "startup": "初创公司", "valuation": "估值", "ipo": "上市",
    "enterprise": "企业", "developer": "开发者",
}


def translate_to_chinese(title: str, summary: str = "") -> tuple[str, str]:
    """
    将英文标题和摘要翻译为中文。
    采用关键词替换策略：保留模型名/公司名等专有名词，翻译常见动词和术语。
    若标题不含任何中文且无法有效翻译，返回空字符串表示跳过。
    """
    if contains_chinese(title):
        # Google News 中文源可能已包含中文标题
        return clean_title(title), clean_summary(summary)

    # 英文标题翻译
    zh_title = title
    zh_summary = summary

    # 按词组长度降序替换（避免短词覆盖长词）
    for en, zh in sorted(TRANSLATIONS.items(), key=lambda x: -len(x[0])):
        zh_title = re.sub(re.escape(en), zh, zh_title, flags=re.IGNORECASE)
        zh_summary = re.sub(re.escape(en), zh, zh_summary, flags=re.IGNORECASE)

    # 首字母大写处理后的残留英文词保留（模型名、公司名等）
    # 检查翻译后是否包含足够的中文
    if not contains_chinese(zh_title):
        # 完全无法翻译，返回空表示跳过
        return "", ""

    return clean_title(zh_title), clean_summary(zh_summary)


def fetch_news():
    """抓取并筛选所有 RSS 源的新闻，中文优先。"""
    items = []
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=24)

    for feed_info in FEEDS:
        try:
            feed = feedparser.parse(feed_info["url"])
            if feed.bozo and not feed.entries:
                print(f"  [警告] RSS 源异常: {feed_info['name']}")
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
                    published = now

                if published < cutoff:
                    continue

                title = entry.get("title", "").strip()
                link = entry.get("link", "").strip()
                summary = entry.get("summary", "")
                if not title or not link:
                    continue
                if not is_ai_related(title, summary):
                    continue

                # 英文新闻翻译处理
                if feed_info["lang"] == "en" or not contains_chinese(title):
                    zh_title, zh_summary = translate_to_chinese(title, summary)
                    if not zh_title:
                        # 无法翻译，跳过该条
                        continue
                    title = zh_title
                    summary = zh_summary
                else:
                    title = clean_title(title)
                    summary = clean_summary(summary)

                items.append({
                    "title": title,
                    "link": link,
                    "summary": summary,
                    "source": feed_info["name"],
                    "published": published,
                    "category": classify(title),
                    "is_chinese": contains_chinese(title),
                    "is_domestic": is_domestic(title, summary),
                })
        except Exception as e:
            print(f"  [错误] {feed_info['name']}: {e}")

    items.sort(key=lambda x: x["published"], reverse=True)

    # 中文优先 + 国内优先选择
    chinese_items = [i for i in items if i["is_chinese"]]
    translated_items = [i for i in items if not i["is_chinese"]]

    # 国内中文新闻（最高优先级）→ 国外中文 → 翻译英文
    domestic_chinese = [i for i in chinese_items if i.get("is_domestic")]
    foreign_chinese = [i for i in chinese_items if not i.get("is_domestic")]

    selected = []
    # 第一轮：国内中文条目，每类最多 2 条
    for cat in ("模型", "热点", "行业", "论文"):
        cat_items = [i for i in domestic_chinese if i["category"] == cat and i not in selected]
        selected.extend(cat_items[:2])
    # 第二轮：国内中文条目填充剩余名额
    for item in domestic_chinese:
        if len(selected) >= 8:
            break
        if item not in selected:
            selected.append(item)
    # 第三轮：国外中文条目补充
    for item in foreign_chinese:
        if len(selected) >= 8:
            break
        if item not in selected:
            selected.append(item)
    # 第四轮：仍不足时用翻译后的英文条目补充
    for item in translated_items:
        if len(selected) >= 8:
            break
        if item not in selected:
            selected.append(item)

    return selected[:8]


def generate_block(items, date_str):
    """
    生成新闻 HTML 区块。
    
    格式规定：
    1. 日期标题使用 dhead/ddate/dbadge 结构
    2. 新闻分为"🇨🇳 国内"和"🌍 国外"两个区域，国内在前
    3. 每条新闻使用 cat/body/h4/p/src 结构
    4. 标题必须可点击（<a> 标签）
    5. 来源必须可点击
    """
    # 按国内外分组
    domestic = [i for i in items if i.get("is_domestic")]
    foreign = [i for i in items if not i.get("is_domestic")]

    # 判断时段标签
    period = "早间" if "早间" in date_str else ("晚间" if "晚间" in date_str else "更新")

    lines = [
        '    <div class="news-day">',
        '      <div class="dhead">',
        f'        <span class="ddate">{date_str}</span>',
        f'        <span class="dbadge">{period}</span>',
        '      </div>',
    ]

    def render_item(item):
        cat_css = CAT_CSS.get(item["category"], "c-model")
        title = html.escape(item["title"])
        summary = html.escape(item["summary"])
        link = item["link"]
        source = item["source"]
        return [
            '      <div class="news-item">',
            f'        <span class="cat {cat_css}">{item["category"]}</span>',
            '        <div class="body">',
            f'          <h4><a href="{link}" target="_blank" rel="noopener">{title}</a></h4>',
            f'          <p>{summary}</p>',
            f'          <span class="src">来源：<a href="{link}" target="_blank" rel="noopener">{source}</a></span>',
            '        </div>',
            '      </div>',
        ]

    # 国内新闻（在前）
    if domestic:
        lines.extend([
            '',
            '      <div class="news-region">',
            '        <span class="region-tag region-cn">🇨🇳 国内</span>',
            '      </div>',
        ])
        for item in domestic:
            lines.extend(render_item(item))

    # 国外新闻（在后）
    if foreign:
        lines.extend([
            '',
            '      <div class="news-region">',
            '        <span class="region-tag region-global">🌍 国外</span>',
            '      </div>',
        ])
        for item in foreign:
            lines.extend(render_item(item))

    lines.append("    </div>")
    return "\n".join(lines)


def update_news_html(block):
    """在 __DAILY_INSERT__ 标记后插入新闻区块。"""
    path = Path("news.html")
    content = path.read_text(encoding="utf-8")
    marker = "<!-- __DAILY_INSERT__"
    if marker not in content:
        print("错误：未找到插入标记")
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

    # 判断时段：14:00 前为早间，之后为晚间
    period = "早间" if now_bj.hour < 14 else "晚间"
    date_label = f"{date_str} {period}更新"

    # 跳过已存在的时段
    news_path = Path("news.html")
    content = news_path.read_text(encoding="utf-8")
    if date_label in content:
        print(f"{date_label} 的新闻已存在，跳过。")
        return

    print(f"正在抓取 {date_label} 的 AI 新闻（中文优先）...")
    items = fetch_news()
    if not items:
        print("未找到 AI 相关新闻，跳过。")
        return

    chinese_count = sum(1 for i in items if i.get("is_chinese"))
    domestic_count = sum(1 for i in items if i.get("is_domestic"))
    foreign_count = len(items) - domestic_count
    print(f"找到 {len(items)} 条相关新闻（中文 {chinese_count} 条，国内 {domestic_count} 条，国外 {foreign_count} 条）")
    block = generate_block(items, date_label)
    if update_news_html(block):
        print(f"✓ news.html 已更新：{date_label}")
    else:
        print("✗ news.html 更新失败")


if __name__ == "__main__":
    main()
