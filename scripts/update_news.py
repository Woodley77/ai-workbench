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
3. 抓取源全部为国内可直连媒体（量子位/爱范儿/IT之家/极客公园），
   原文链接国内无需代理即可打开；海外公司动态由国内媒体转译报道后，
   经 is_domestic 判定自然落入「🌍 国外」区，链接仍可直连。
══════════════════════════════════════════════════════════════

══════════════════════════════════════════════════════════════
按主题分模块（v17 起，2026-09-09）
══════════════════════════════════════════════════════════════
动态区（news.html 每日动态）不再是一天一坨混排时间线，而是四个
主题模块，各自独立归档、每日自动追加（每天 08:23/18:23 两次）：
  ① __DYN_AGENT_INSERT__  → 🤖 智能体动态（智能体应用/Agent 产品/生态开源）
  ② __DYN_MODEL_INSERT__  → 🦾 大模型动态（模型发布/升级开源/调价评测）
  ③ __DYN_TOOLS_INSERT__  → 🧩 技能与 MCP（Agent Skills/MCP/插件生态）
  ④ __DYN_MISC_INSERT__   → 📰 综合要闻（行业事件/论文/大公司动态，兜底）
抓取条目先按标题关键词归档（topic_for_title），同一时段内每个模块
各自生成一个区块（块内仍按 🇨🇳国内/🌍国外 分区），插入对应 marker。
防重按「模块区」粒度：某模块该 date_label（YYYY-MM-DD 早间/晚间）已存在则跳过。
首页「今日动态」卡改为四个模块各取最新 1 条。
══════════════════════════════════════════════════════════════

══════════════════════════════════════════════════════════════
每日新闻展示格式规范（严格遵循，不可违反）
══════════════════════════════════════════════════════════════

一、HTML 结构层级（每个日报区块）
─────────────────────────────────
<div class="news-day">
  <div class="dhead">
    <span class="ddate">YYYY-MM-DD 时段更新</span>
    <span class="dbadge">早间|晚间</span>
  </div>

  <!-- 国内区域（必须在国外之前） -->
  <div class="news-region">
    <span class="region-tag region-cn">🇨🇳 国内</span>
  </div>
  <div class="news-item"> ... </div>
  ...

  <!-- 国外区域（在国内之后） -->
  <div class="news-region">
    <span class="region-tag region-global">🌍 国外</span>
  </div>
  <div class="news-item"> ... </div>
  ...
</div>

二、单条新闻结构
─────────────────────────────────
<div class="news-item">
  <span class="cat {分类CSS}">{分类名}</span>
  <div class="body">
    <h4><a href="{链接}" target="_blank" rel="noopener">{标题}</a></h4>
    <p>{摘要}</p>
    <span class="src">来源：<a href="{链接}" target="_blank" rel="noopener">{来源名}</a></span>
  </div>
</div>

三、格式强制要求
─────────────────────────────────
1. 【国内外分区】每个日报区块必须分为"🇨🇳 国内"和"🌍 国外"两个区域
2. 【国内优先】国内新闻必须放在国外新闻之前，不可颠倒
3. 【国内为主】国内新闻数量应不少于国外新闻，国内 ≥ 国外
4. 【标题可点击】所有新闻标题必须使用 <a> 标签包裹，链接到原文
5. 【来源可点击】所有来源必须使用 <a> 标签包裹，链接到原文
6. 【链接安全】所有 <a> 标签必须包含 target="_blank" rel="noopener"
7. 【分类标签】每条新闻必须有分类标签（模型/热点/行业/论文）
8. 【中文标题】标题和摘要必须为中文（英文专有名词除外）
9. 【时段标签】dbadge 使用"早间"或"晚间"
10.【区域标签】region-cn 为绿色，region-global 为蓝色

四、分类标签 → CSS 映射
─────────────────────────────────
模型 → c-model
热点 → c-news
行业 → c-event
论文 → c-paper

五、国内外判定规则
─────────────────────────────────
国内（is_domestic=True）：标题或摘要包含以下关键词
  DeepSeek, Qwen, 通义千问, 阿里, 智谱, GLM, 字节, 豆包,
  腾讯, 混元, 华为, 昇腾, 商汤, 百度, 文心, Kimi, 月之暗面,
  MiniMax, 美团, 京东, 杭州, 浙江, 深圳, 北京, 上海, 国产
国外（is_domestic=False）：不包含上述关键词的新闻
══════════════════════════════════════════════════════════════
"""

import feedparser
import html
import re
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ── RSS 源（全部为国内可直连媒体，2026-09-09 起弃用 Google News / 英文源：
#    原 Google News 搜索链接为 news.google.com 跳转壳，国内用户无法打开；
#    英文源（HN/TechCrunch）原文亦多需代理。国内媒体会同步报道海外公司动态，
#    经 is_domestic 判定后自然落入「🌍 国外」区，链接仍是国内可直连的原文。）─
FEEDS = [
    {"url": "https://www.qbitai.com/feed",     "name": "量子位",   "lang": "zh"},
    {"url": "https://www.ifanr.com/feed",      "name": "爱范儿",   "lang": "zh"},
    {"url": "https://www.ithome.com/rss/",     "name": "IT之家",   "lang": "zh"},
    {"url": "https://www.geekpark.net/rss",    "name": "极客公园", "lang": "zh"},
]

FEED_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
           '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')
FEED_TIMEOUT = 20  # 单源抓取超时秒数：CI runner 在海外访问国内源，防个别源拖垮整个 job

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
    "deepseek", "qwen", "通义千问", "千问", "阿里", "alibaba", "智谱", "glm", "z.ai",
    "字节", "bytedance", "豆包", "doubao", "腾讯", "tencent", "混元", "hunyuan",
    "华为", "huawei", "昇腾", "ascend", "商汤", "sensetime", "sensenova",
    "百度", "baidu", "文心", "ernie", "kimi", "月之暗面", "moonshot",
    "minimax", "美团", "meituan", "京东", "jd.com",
    "字节跳动", "veGiantModel", "seedrealtime", "welM", "华为昇腾",
    "蚂蚁", "百灵", "科大讯飞", "讯飞", "腾讯云", "阿里云", "百度智能云",
    "杭州", "浙江", "深圳", "北京", "上海", "国产", "国内",
]


def contains_chinese(text: str) -> bool:
    """检查文本是否包含中文字符。"""
    return bool(re.search(r'[\u4e00-\u9fff]', text))


# ── 主题模块关键词（v17：动态区按主题分模块归档）──────────────────────
# 优先级：agent > model > tools，都不中则落 misc（综合要闻兜底）
AGENT_TOPIC_KW = [
    "智能体", "助手", "数字员工", "扣子", "coze", "dify", "机器人",
    "agentic", "ai agent", "agents", "agent", "muse",
]
MODEL_TOPIC_KW = MODEL_KW  # 复用原「模型」分类词表
TOOLS_TOPIC_KW = [
    "mcp", "model context protocol", "skill", "skills", "插件",
    "function calling", "工具调用", "workflow",
]


def topic_for_title(title: str) -> str:
    """把标题归档到主题模块：agent / model / tools / misc。"""
    t = title.lower()
    if re.search(r'(?<![a-z])agent(?![a-z])', t) or any(k in t for k in AGENT_TOPIC_KW):
        return "agent"
    if any(k in t for k in TOOLS_TOPIC_KW):
        return "tools"
    if any(k in t for k in MODEL_TOPIC_KW):
        return "model"
    return "misc"


# 主题模块注册表：marker → topic → 展示名（顺序即 news.html 模块顺序）
MODULES = [
    ("__DYN_AGENT_INSERT__", "agent",  "智能体动态"),
    ("__DYN_MODEL_INSERT__", "model",  "大模型动态"),
    ("__DYN_TOOLS_INSERT__", "tools",  "技能与 MCP"),
    ("__DYN_MISC_INSERT__",  "misc",   "综合要闻"),
]

# ── 归档区（news.html 的另外三个 tab：新模型速报/行业大事记/论文快报）────
# 有命中才更新（无则跳过），与四模块共用每日抓取。三个区互斥：release=模型发布/预告，
# milestone=产业级大事，paper=论文研究。避免把同一条重复写进两个归档区。
ARCHIVES = [
    # (marker, key, 展示名, 选稿上限, 判定函数)
    ("__RELEASE_INSERT__", "release",  "新模型速报", 3, "is_release_item"),
    ("__MILESTONE_INSERT__", "milestone", "行业大事记", 4, "is_milestone_item"),
    ("__PAPERS_INSERT__", "paper",    "论文快报", 3, "is_paper_item"),
]

# 发布信号词（标题须含其一，且再满足「模型信号」才算新模型速报）
RELEASE_SIGNAL = ["发布", "预告", "上线", "公测", "内测", "正式版", "开源", "亮相", "推出", "开售"]
# 模型信号：具体模型名或"模型"类词
RELEASE_MODEL_NAME = ["gpt", "chatgpt", "claude", "gemini", "deepseek", "qwen", "kimi",
                      "glm", "混元", "豆包", "minimax", "文心", "百灵", "llama", "模型",
                      "大模型", "v4", "v4.1", "v5", "flash", "opus", "sonnet", "haiku",
                      "aistudio", "images", "sora", "veo", "seedance"]
# 大事记强词：产业/公司级信号（标题导向；模型发布已被 release 收走，避免泛社会新闻）
MILESTONE_KW = ["ipo", "上市", "融资", "收购", "并购", "关停", "下架", "退出", "禁令",
                "立法", "制裁", "政策", "官宣", "登顶", "破纪录", "刷新纪录", "sota",
                "榜单第一", "排行第一", "财报", "市值", "股价", "裁员", "重组", "起诉",
                "判决", "监管", "框架协议", "战略合作", "成立新公司"]


def is_release_item(item) -> bool:
    t = (item["title"]).lower()
    if not any(k in t for k in RELEASE_SIGNAL):
        return False
    # 排除纯 API/平台类开放消息（无新模型实体的发布），保留模型名/版本号命中
    return any(k in t for k in RELEASE_MODEL_NAME)


def is_milestone_item(item) -> bool:
    # 标题导向 + 要求长度足够（过滤一句话新闻），避免把琐碎社会新闻当大事
    t = item["title"].lower()
    return len(item["title"]) >= 18 and any(k in t for k in MILESTONE_KW)


def is_paper_item(item) -> bool:
    # 严格标题导向：只收明确学术形态的条目（论文/技术报告/系统卡/基准/学术）
    t = item["title"].lower()
    return any(k in t for k in ["论文", "arxiv", "技术报告", "系统卡", "benchmark",
                                "基准测试", "学术", "预印本", "研究发现", "研究团队",
                                "发布研究", "研究称"])


def archive_for(key: str) -> str:
    """返回归档 marker 全前缀（含注释）。"""
    for mk, k, _label, _cap, _fn in ARCHIVES:
        if k == key:
            return f"<!-- {mk}"
    raise ValueError(key)


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


# 摘要侧的「强信号」词：标题没命中时，仅当摘要含这些才放行（避免泛 AI 词误放）
SUMMARY_STRONG_KW = [
    "人工智能", "大模型", "大语言模型", "智能体", "深度学习", "生成式",
    "多模态", "llm", "gpt", "chatgpt", "deepseek", "openai", "claude",
    "gemini", "agent", "aigc", "diffusion", "transformer", "神经网络",
    "机器学习", "模型", "推理芯片", "算力", "算法",
]


def is_ai_related(title: str, summary: str = "") -> bool:
    """判断新闻是否与 AI 相关。

    标题导向：标题必须命中 AI 关键词；标题未命中时，摘要需含『强信号』词
    才放行（如 人工智能/大模型/智能体/模型/gpt 等），杜绝摘要里泛 'ai'
    字样就误放手机/电商/会员类新闻。

    附加排除：多主题早报/晚报合集（形如「早报｜A/B/C」）即便含片段 AI 词
    也拒绝——合集首屏多是非 AI 的消费电子消息，主题不纯。
    """
    t = title.lower()
    s = summary.lower()
    if re.match(r'^(早报|晚报|午报|快讯)｜', title) or re.match(r'^(早报|晚报|午报|快讯)\|', t):
        return False
    if any(kw in t for kw in AI_KEYWORDS):
        return True
    return any(kw in s for kw in SUMMARY_STRONG_KW)


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
            req = urllib.request.Request(
                feed_info["url"],
                headers={"User-Agent": FEED_UA,
                         "Accept": "application/rss+xml, application/xml, text/xml, */*"},
            )
            with urllib.request.urlopen(req, timeout=FEED_TIMEOUT) as resp:
                raw = resp.read().decode("utf-8", "ignore")
            feed = feedparser.parse(raw)
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
    return items


def select_items(items, cap=6):
    """对单个主题桶做选稿：源均衡(cap2/源) + 国内优先 + 国内 ≥ 国外 + 总量 cap。

    返回按时间倒序的最终列表（domestic 在前）。
    """
    per_source_cap = 2

    def balanced(arr):
        cnt = {}
        out = []
        for it in arr:  # arr 已按时间倒序，先到先得 = 优先取最新
            if cnt.get(it["source"], 0) >= per_source_cap:
                continue
            out.append(it)
            cnt[it["source"]] = cnt.get(it["source"], 0) + 1
        return out

    chinese_items = [i for i in items if i.get("is_chinese")]
    translated_items = [i for i in items if not i.get("is_chinese")]

    domestic_chinese = balanced([i for i in chinese_items if i.get("is_domestic")])
    foreign_chinese = balanced([i for i in chinese_items if not i.get("is_domestic")])

    selected = []
    # 第一轮：国内中文条目（按原分类轮询，每类至多 2，保证覆盖面）
    for cat in ("模型", "热点", "行业", "论文"):
        cat_items = [i for i in domestic_chinese if i["category"] == cat and i not in selected]
        selected.extend(cat_items[:2])
    # 第二轮：国内中文条目填充剩余名额
    for item in domestic_chinese:
        if len(selected) >= cap:
            break
        if item not in selected:
            selected.append(item)
    # 第三轮：国外中文条目补充（桶内无国内条目时允许全国外，否则国外 ≤ 国内）
    domestic_count = len(selected)
    for item in foreign_chinese:
        if len(selected) >= cap:
            break
        if domestic_count > 0 and len(selected) - domestic_count >= domestic_count:
            break
        if item not in selected:
            selected.append(item)
    # 第四轮：翻译英文条目兜底（英文源已弃用，保留以防未来恢复）
    domestic_count = sum(1 for i in selected if i.get("is_domestic"))
    foreign_count = len(selected) - domestic_count
    for item in translated_items:
        if len(selected) >= cap:
            break
        if not item.get("is_domestic") and foreign_count >= domestic_count:
            continue
        if item not in selected:
            selected.append(item)
            if not item.get("is_domestic"):
                foreign_count += 1
    # 稳定：国内在前
    return sorted(selected[:cap], key=lambda x: (not x.get("is_domestic"), x["published"]), reverse=True)


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


def insert_module(block, marker, label, date_label):
    """把 block 插入 news.html 指定 marker 注释行之后。

    marker 示例：'<!-- __DYN_AGENT_INSERT__'、'<!-- __RELEASE_INSERT__'。
    防重粒度 = 区段：从本 marker 到下一个 HTML 注释 marker（<!-- __XXX_INSERT__）
    之间的文本，若已含 date_label（如「2026-09-09 晚间更新」）则跳过——
    每个模块/归档区可各自拥有同日同段的块，互不干扰。
    """
    path = Path("news.html")
    content = path.read_text(encoding="utf-8")
    if marker not in content:
        print(f"错误：未找到标记 {marker}，跳过 {label}")
        return False

    idx = content.find(marker)
    # 区段终点：自 idx 起第一个后续注释 marker（<!-- __…_INSERT__）；无则到 </section> 或文件尾
    nxt = len(content)
    for m in re.finditer(r'<!--\s*__[A-Za-z]+_INSERT__', content):
        if m.start() > idx and m.start() < nxt:
            nxt = m.start()
    if nxt == len(content):
        end_sec = content.find("</section>", idx)
        nxt = end_sec if end_sec != -1 else len(content)

    section_text = content[idx:nxt]
    if f'<span class="ddate">{date_label}</span>' in section_text:
        print(f"· {label} {date_label} 已存在，跳过（防重）")
        return False

    # 在 marker 所在行的行尾之后插入 block
    line_end = content.find("\n", idx)
    if line_end == -1:
        line_end = idx
    content = content[:line_end + 1] + block + "\n" + content[line_end + 1:]
    path.write_text(content, encoding="utf-8")
    return True


def update_homepage(items, date_label):
    """
    联动更新首页 index.html 的「今日 AI 动态」卡片。

    格式规定：
    1. 卡片内容位于 __TODAY_CARD__ / __END_TODAY_CARD__ 标记之间
    2. 接收四个主题模块的代表列表（≤4 条，各模块最新 1 条）
    3. 每条格式：<li><b>分类</b> · 🇨🇳/🌍：<a>标题</a></li>，标题截断 60 字
    4. 徽标更新为「更新于 {date_label}」
    """
    path = Path("index.html")
    if not path.exists():
        print("警告：index.html 不存在，跳过首页更新")
        return False
    content = path.read_text(encoding="utf-8")

    start_marker = "<!-- __TODAY_CARD__ -->"
    end_marker = "<!-- __END_TODAY_CARD__ -->"
    if start_marker not in content or end_marker not in content:
        print("警告：首页未找到 __TODAY_CARD__ 标记，跳过首页更新")
        return False

    lis = []
    for item in items[:4]:
        region = "🇨🇳" if item.get("is_domestic") else "🌍"
        title = html.escape(item["title"][:60])
        lis.append(
            f'        <li><b>{item["category"]}</b> · {region}：'
            f'<a href="{item["link"]}" target="_blank" rel="noopener">{title}</a></li>'
        )
    card = "      <ul>\n" + "\n".join(lis) + "\n      </ul>"

    start = content.index(start_marker) + len(start_marker)
    end = content.index(end_marker)
    content = content[:start] + "\n" + card + "\n      " + content[end:]

    # 更新徽标时间
    content = re.sub(
        r'(<span[^>]*data-news-badge[^>]*>)[^<]*(</span>)',
        rf'\g<1>更新于 {date_label}\g<2>',
        content,
    )

    path.write_text(content, encoding="utf-8")
    return True


def main():
    """入口：整体容错——任何意外错误只打印，不让 CI job 中断（否则 update_content 不会执行）。"""
    try:
        _main_inner()
    except Exception as e:
        print(f"✗ update_news 意外错误（已跳过，update_content 将继续）: {e}")


def _main_inner():
    beijing_tz = timezone(timedelta(hours=8))
    now_bj = datetime.now(beijing_tz)
    date_str = now_bj.strftime("%Y-%m-%d")

    # 判断时段：14:00 前为早间，之后为晚间
    period = "早间" if now_bj.hour < 14 else "晚间"
    date_label = f"{date_str} {period}更新"

    print(f"正在抓取 {date_label} 的 AI 新闻（国内源，按主题归档）...")
    items = fetch_news()
    if not items:
        print("未找到 AI 相关新闻，跳过。")
        return

    chinese_count = sum(1 for i in items if i.get("is_chinese"))
    domestic_count = sum(1 for i in items if i.get("is_domestic"))
    print(f"抓到 {len(items)} 条 AI 候选（中文 {chinese_count} 条，国内 {domestic_count} 条）")

    # 按主题归档
    buckets = {"agent": [], "model": [], "tools": [], "misc": []}
    for it in items:
        buckets.setdefault(topic_for_title(it["title"]), []).append(it)
    for topic in ("agent", "model", "tools", "misc"):
        print(f"  [{topic}] 候选 {len(buckets[topic])} 条")

    # 每个模块独立选稿 + 插入（防重按区段）；首页代表 = 各模块最终入选首条
    any_inserted = False
    picks = []
    for marker, topic, label in MODULES:
        sel = select_items(buckets.get(topic, []), cap=6)
        if not sel:
            print(f"· {label}（{topic}）今日无合适内容，跳过")
            continue
        block = generate_block(sel, date_label)
        if insert_module(block, f"<!-- {marker}", label, date_label):
            print(f"✓ news.html [{label}] 已追加 {date_label}（{len(sel)} 条）")
            any_inserted = True
        picks.append(sel[0])  # 代表（模块已写或已存在都取同一条，保证首页与页面一致）

    # 三个归档区（速报/大事记/论文）：有命中才更新，无命中跳过
    archive_fns = {"release": is_release_item, "milestone": is_milestone_item, "paper": is_paper_item}
    for mk, key, label, cap, fn_name in ARCHIVES:
        fn = archive_fns[key]
        cand = [it for it in items if fn(it)]
        if not cand:
            print(f"· {label}（{key}）今日无命中条目，跳过")
            continue
        # 去重（同一标题可能多条），源均衡后再选
        seen_titles, uniq = set(), []
        for it in cand:
            if it["title"] in seen_titles:
                continue
            seen_titles.add(it["title"])
            uniq.append(it)
        sel = select_items(uniq, cap=cap)
        if not sel:
            print(f"· {label}（{key}）无合适内容，跳过")
            continue
        block = generate_block(sel, date_label)
        if insert_module(block, f"<!-- {mk}", label, date_label):
            print(f"✓ news.html [{label}] 已追加 {date_label}（{len(sel)} 条）")
            any_inserted = True

    # 首页「今日 AI 动态」：pick 顺序 = agent/model/tools/misc
    if picks:
        if update_homepage(picks, date_label):
            print(f"✓ index.html 首页「今日 AI 动态」已联动更新（{len(picks)} 条代表）")
        else:
            print("✗ index.html 首页联动更新失败")

    if not any_inserted:
        print(f"{date_label} 所有模块均已存在或无可写内容，无改动。")


if __name__ == "__main__":
    main()
