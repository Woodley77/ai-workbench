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
按国内外分两大模块（v19 起，2026-09-09）
══════════════════════════════════════════════════════════════
动态区（news.html 每日动态）不做主题细分，只按国内外分两个模块，
各自独立归档、每日自动追加（每天 08:23/18:23 两次）：
  ① __DOMESTIC_INSERT__ → 🇨🇳 国内动态（国产模型/厂商/产品，is_domestic=True）
  ② __FOREIGN_INSERT__  → 🌍 国外动态（OpenAI/Anthropic/Google 等海外动态）
抓取条目直接按 is_domestic 归属两个桶，各自选稿生成区块插入对应 marker。
防重按「模块区」粒度：该模块该 date_label（YYYY-MM-DD 早间/晚间）已存在则跳过。
首页「今日动态」卡取国内、国外各 2 条代表。
══════════════════════════════════════════════════════════════

══════════════════════════════════════════════════════════════
新闻侧重策略（v20 起，2026-09-09）
══════════════════════════════════════════════════════════════
在不改板块结构的前提下，给「抓取过滤 + 选稿排序」加侧重：
  ① 滤噪：边缘弱关联 AI（智能汽车/消费数码/泛娱乐等贴牌新闻）在抓取层滤除，
     只保留主流 AI 厂商/模型的核心动态浓度；
  ② 优先：主流 AI 公司白名单（AI_COMPANY_WHITELIST，头部 ~20 家）与
     模型发布/重磅形态（_release_form）的条目在选稿时加权优先入选，
     权重相同者仍按时间倒序取新。
过滤/加权仅作用于 update_news.py 内部，news.html 结构与 marker 完全不变。
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
import json
import os
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
    # v21 扩充（均为国内可直连 + 海外 runner 实测可达；V2EX/Reddit 超时、
    # Anthropic 无 RSS、机器之心 feed 失效 → 不加）
    {"url": "https://sspai.com/feed",           "name": "少数派",   "lang": "zh"},
    {"url": "https://www.infoq.cn/feed",        "name": "InfoQ",   "lang": "zh"},
    {"url": "https://www.oschina.net/news/rss", "name": "开源中国", "lang": "zh"},
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
    # v19 补充：标题导向的国产主体词（避免产业/政策/车企动态被误判为国外）
    "我国", "鸿蒙", "问界", "麒麟", "小米", "xiaomi", "荣耀", "oppo", "vivo",
    "大疆", "dji", "中兴", "地平线", "寒武纪", "摩尔线程", "海光", "龙芯", "飞腾",
    "中芯", "长鑫", "长江存储", "紫光", "新华三", "浪潮", "联想", "中国信通院",
    "天马", "京东方", "维信诺", "华星", "tcl华星",
]


def contains_chinese(text: str) -> bool:
    """检查文本是否包含中文字符。"""
    return bool(re.search(r'[\u4e00-\u9fff]', text))


# ── 动态区模块（v19：不做主题细分，只按国内外分两块）────────────────
# is_domestic 判定见 DOMESTIC_KW：国产模型/厂商相关 → 国内动态，其余 → 国外动态
MODULES = [
    ("__DOMESTIC_INSERT__", "domestic", "国内动态"),
    ("__FOREIGN_INSERT__",  "foreign",  "国外动态"),
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


# ── 主流 AI 公司白名单（v20 侧重：头部 ~20 家，命中 = 重点关注，选稿加权 +2）──
# 国外 10 家 + 国内 10 家。词表给出公司名/核心产品/模型的常用写法（匹配小写化后的
# 标题+摘要）。刻意不放 iphone/windows/kindle 等终端品类名，避免贴牌消费新闻冒充
# 公司动态；如需扩充公司，直接往对应分组追加别名即可。
AI_COMPANY_WHITELIST = [
    # 国外：OpenAI / Anthropic / Google(DeepMind) / Meta / Microsoft /
    #       NVIDIA / xAI / Amazon / Apple / Mistral
    "openai", "chatgpt", "anthropic", "claude",
    "google", "谷歌", "deepmind", "gemini",
    "meta", "facebook", "llama",
    "microsoft", "微软", "copilot", "azure",
    "nvidia", "英伟达", "黄仁勋",
    "xai", "grok",
    "amazon", "aws", "alexa", "亚马逊",
    "apple", "苹果", "apple intelligence", "siri",
    "mistral",
    # 国内：DeepSeek / 阿里(通义千问) / 字节(豆包) / 腾讯(混元) / 百度(文心) /
    #       智谱(GLM) / 月之暗面(Kimi) / MiniMax(海螺) / 华为(昇腾·盘古) / 商汤(日日新)
    "deepseek", "阿里", "alibaba", "通义", "qwen", "千问",
    "字节", "bytedance", "豆包", "doubao",
    "腾讯", "tencent", "混元", "hunyuan",
    "百度", "baidu", "文心", "ernie",
    "智谱", "glm", "z.ai",
    "月之暗面", "moonshot", "kimi",
    "minimax", "海螺",
    "华为", "huawei", "昇腾", "ascend", "盘古",
    "商汤", "sensetime", "日日新",
]


# ── 噪声关键词（v20 滤噪：贴牌泛 AI 的边缘科技）────────────────────────
# 命中 NOISE_KW 的条目若标题不含核心保护词、又不属白名单公司/模型发布形态，
# 即判为噪声在抓取层滤除——这类新闻只是带了 'AI' 字样，主体是智能汽车/消费
# 数码/家电/泛娱乐等，收进来会稀释「主流 AI 公司行动」的侧重浓度。
NOISE_KW = [
    # 智能汽车 / 出行
    "汽车", "车型", "新车", "suv", "智能驾驶", "智驾", "自动驾驶", "座舱", "续航",
    "问界", "理想汽车", "小鹏", "蔚来", "极氪", "比亚迪", "特斯拉", "tesla",
    "小米su7", "小米汽车", "路测",
    # 消费数码终端
    "手机", "iphone", "智能手机", "旗舰", "平板", "笔记本", "笔电", "耳机",
    "智能手表", "智能眼镜", "ar眼镜", "vr", "头显", "电视", "显示器", "屏幕",
    "折叠屏", "投影",
    # v21：消费电子品牌/系统（避免「AirPods 升级」「watchOS 更新日志」这类
    # 被 MODEL_INTEL_KW 的"更新/升级"误当成模型情报）
    "airpods", "watchos", "ios 27", "ios 26", "ipados", "macos", "macbook",
    "imac", "ipad", "airtag", "homepod", "apple watch", "surface", "pixel",
    "galaxy", "鸿蒙 os", "系统更新", "固件", "更新日志", "rc 版", "rc 候选",
    # 家电 / 泛消费
    "家电", "空调", "冰箱", "洗衣机", "扫地机", "电动牙刷",
    # 泛娱乐 / 金融边缘
    "游戏", "电竞", "比特币", "区块链", "web3", "nft", "数字货币",
]

# 硬噪声词（v21）：消费电子整机/系统版本类。命中即判噪声，**优先级高于白名单**
# ——否则「苹果 AirPods 5 发布」「watchOS 更新日志」会因为 Apple 在白名单里被救回，
# 再被 MODEL_INTEL_KW 的"发布/更新"误当成模型情报。仅当标题同时含硬保护词
# （真·模型/Agent/API 词）时才放行，如「Apple Intelligence 接入 GPT-5」。
HARD_NOISE_KW = [
    "airpods", "watchos", "ipados", "macos", "macbook", "imac", "airtag",
    "homepod", "apple watch", "iphone", "surface", "pixel", "galaxy",
    "鸿蒙 os", "harmonyos", "系统更新", "固件", "更新日志", "rc 版", "rc 候选",
    "返校季", "以旧换新", "国补", "销量", "出货量",
]

# 硬保护词：与 HARD_NOISE_KW 同时命中则放行（消费电子新闻里夹带真模型情报）
HARD_SAFE_KW = [
    "模型", "大模型", "智能体", "agent", "gpt", "chatgpt", "claude", "gemini",
    "deepseek", "qwen", "kimi", "glm", "llama", "api", "推理", "多模态",
    "开源权重", "微调", "sota", "跑分",
]

# 核心保护词（标题命中其一则绝不判噪声）：真实模型名/强主题词，避免误伤
NOISE_SAFE_KW = [
    "模型", "大模型", "智能体", "agent", "gpt", "chatgpt", "claude", "gemini",
    "deepseek", "qwen", "kimi", "glm", "llama", "openai", "anthropic", "mistral",
    "多模态", "生成式", "sora", "veo", "seedance", "推理", "算力", "芯片",
    "aigc", "open source", "开源模型",
]


# ── v21 收录口径（用户口径 v2）：只收「能直接用的模型/产品情报」────────────
# 加分项：模型发布与版本更新、API 定价/倍率/限免/免费额度、订阅政策变动、
# 工具与 Agent 产品上线更新、开源权重与规格、模型实测跑分。
MODEL_INTEL_KW = [
    # 模型与版本
    "模型", "大模型", "语言模型", "多模态", "权重", "开源", "上下文", "参数",
    "版本", "升级", "更新", "发布", "推出", "上线", "公测", "内测", "灰度",
    "正式版", "preview", "beta", "release", "changelog",
    # 定价与订阅（用户最关心）
    "api", "接口", "定价", "价格", "倍率", "免费", "限免", "免费额度", "额度",
    "订阅", "套餐", "会员", "收费", "涨价", "降价", "下调", "优惠", "折扣",
    "计费", "token 价格", "token", "充值", "额度赠送",
    # 产品与能力
    "客户端", "app", "插件", "agent", "智能体", "助手", "助手功能",
    "跑分", "评测", "基准", "榜单", "sota", "benchmark",
]

# 减分项：产业面新闻（用户明确"不是重点"：某公司在某地做了什么）
INDUSTRY_NOISE_KW = [
    "融资", "ipo", "上市", "科创板", "收购", "并购", "领投", "估值", "股价",
    "财报", "市值", "合作", "战略合作", "达成合作", "签约", "协议",
    "数据中心", "算力集群", "智算中心", "机房", "电力", "核电站", "光伏",
    "调查", "反垄断", "法案", "立法", "监管", "制裁", "禁令", "诉讼", "起诉",
    "演讲", "表示", "认为", "警告", "访谈", "对话", "观点", "大会", "峰会", "论坛",
]


def is_key_company(title: str, summary: str = "") -> bool:
    """是否命中主流 AI 公司白名单（国内外头部厂商的核心动态）。"""
    text = (title + " " + summary).lower()
    return any(kw in text for kw in AI_COMPANY_WHITELIST)


def _release_form(title: str) -> bool:
    """标题级判定：模型发布/预告/重磅形态（发布类信号词 + 模型名/产品词）。
    语义与原 is_release_item 一致，供「速报」判定与 v20 加权排序共用。"""
    t = title.lower()
    return any(k in t for k in RELEASE_SIGNAL) and any(k in t for k in RELEASE_MODEL_NAME)


def is_noise_weak_ai(title: str, summary: str = "") -> bool:
    """边缘弱关联 AI 滤除。返回 True 表示判为噪声、应跳过。

    判定链：① 命中 HARD_NOISE_KW 且不含 HARD_SAFE_KW → 噪声（消费电子整机/
    系统版本，白名单也救不回）；② 未命中 NOISE_KW → 放行；③ 标题含核心保护词
    → 放行；④ 属白名单主流公司 → 放行；⑤ 构成模型发布/重磅形态 → 放行；
    否则（仅 'AI' 字样的贴牌新闻）→ 噪声。
    """
    t = title.lower()
    if any(k in t for k in HARD_NOISE_KW) and not any(k in t for k in HARD_SAFE_KW):
        return True
    if not any(k in t for k in NOISE_KW):
        return False
    if any(k in t for k in NOISE_SAFE_KW):
        return False
    if is_key_company(title, summary):
        return False
    return not _release_form(title)


def _priority_score(item) -> int:
    """v21 侧重分（用户口径 v2：只要「能直接用的模型/产品情报」）。

    加分（能动手的）：
      +3 命中模型情报信号（模型发布/版本/定价/倍率/限免/免费额度/订阅变更/API/工具上线/开源权重）
      +2 模型发布·重磅形态（_release_form）
      +1 主流 AI 公司白名单
    减分（能围观的）：
      -3 命中产业面信号（融资/IPO/并购/合作/数据中心/算力集群/监管调查/法案/高管观点/大会）
    越高越优先入选；同分内按时间倒序。缺字段用 .get 兜底。
    """
    s = 0
    if item.get("is_model_intel"):
        s += 3
    if item.get("is_priority_form"):
        s += 2
    if item.get("is_key_company"):
        s += 1
    if item.get("is_industry"):
        s -= 3
    return s


def is_model_intel(title: str, summary: str = "") -> bool:
    """是否属于「模型/产品/定价」类可操作情报（v21 主体收录对象）。"""
    text = (title + " " + (summary or "")).lower()
    return any(k in text for k in MODEL_INTEL_KW)


def is_industry_topic(title: str, summary: str = "") -> bool:
    """是否属于产业面新闻（融资/并购/基建/监管/观点——用户明确不关注）。"""
    text = (title + " " + (summary or "")).lower()
    return any(k in text for k in INDUSTRY_NOISE_KW)


def is_roundup(title: str) -> bool:
    """早报/晚报/速览/盘点类**多主题合集**（信息拼盘，不作为每日要闻收录）。

    合集特征：标题含栏目词（早报/晚报/早知道/早参/速览/盘点/一周要闻…）且
    ① 出现在标题开头，或 ② 标题较长（≥15 字），或 ③ 标题含 ｜/| 分隔符。
    单条新闻几乎不会同时满足这些条件（例：「IT早报 0911：雷军…；DeepSeek…」
    「…特斯拉再降价｜极客早知道」都能被拦下）。
    """
    t = title.strip()
    kws = ("早报", "晚报", "午报", "快讯", "日报", "周报", "早知道", "早参",
           "速览", "盘点", "一周要闻", "要闻回顾", "汇总")
    if not any(k in t for k in kws):
        return False
    if re.match(r'^(IT)?\s*(早报|晚报|午报|快讯|日报|周报|早知道|早参)', t):
        return True
    if len(t) >= 15:
        return True
    return bool(re.search(r'[｜|]', t))


# ═══════════════════════════════════════════════════════════════════════════
# v21 线上 AI 精编（CI 侧语义判断）
# ───────────────────────────────────────────────────────────────────────────
# 背景：用户否掉了纯关键词选稿（"效果不好"），要的是「能直接用的模型情报」，
# 且明确不要在本地跑定时任务（本机关机就断了）。因此把「精编」这一步搬到
# GitHub Actions 里：runner 上跑本脚本时，若仓库配置了 DEEPSEEK_API_KEY
# （daily-update.yml 已注入，update_content.py 也在用同一个 secret），
# 就调 DeepSeek 按用户口径做语义选稿 + 中文标题；没有 Key 或调用失败时，
# 自动退回上面的关键词加权选稿（select_items），保证「每天线上必有产出」。
# 链接永远由脚本从 RSS 按编号回填，AI 无权提供 URL，杜绝编造。
# ═══════════════════════════════════════════════════════════════════════════
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"

CURATE_PROMPT = """你在为一位中文 AI 从业者做每日情报精编。他每天只想知道**能直接用的模型情报**。

【收录口径】只收读了能立刻动手做决定的信息：
1. 模型发布 / 版本更新（新模型、新版本、能力升级、权重新开源、上下文或参数变化）
2. API 定价 / 倍率 / 限免 / 免费额度 / 订阅政策变动（涨价降价、倍率调整、暂停某档订阅、免费开放）
3. 工具与 Agent 产品上线或更新（新客户端、新功能、新插件、新 API 能力、接入某模型）
4. 模型实测跑分 / 基准对比（能据此判断该选哪个模型）

【明确不收】用户说过这些是次要面：
- 产业面：融资 / IPO / 并购 / 财报 / 市值 / 战略合作 / 签约
- 基建面：数据中心 / 算力集群 / 电力 / 机房
- 监管面：调查 / 反垄断 / 法案 / 制裁 / 诉讼
- 观点面：高管发言 / 演讲 / 访谈 / 行业大会峰会论坛
- 泛论面："AI 将如何改变世界"式的评论、与模型使用无关的社会趣闻
判据：**能动手的 > 能围观的**。拿不准时，问自己"读完这条我能改代码 / 改订阅 / 换模型吗"。
另外：早报晚报类多主题合集、消费电子整机（AirPods / watchOS 更新日志 / 手机发布）都不要。

现在是「{region}」候选，请从下面 {total} 条里挑出最值得看的，最多 {cap} 条。
宁缺毋滥——只挑得出 2 条就给 2 条，一条都不够格就给空数组。

【输出格式】只输出 JSON，不要任何解释：
{{"items":[{{"i":候选编号,"title":"中文标题"}}]}}
- 编号 i 必须是上面候选列表里的数字，不许自造。
- title 一律用中文（英文候选请翻译成准确的中文），控制在 40 字内，客观陈述，不加"重磅""炸裂"等形容词。
- 中文候选若原标题已经很好，可原样返回。
- 不要补充候选里没有的信息。

候选列表：
{listing}"""


def ai_curate(items, region_label, cap=6):
    """调 DeepSeek 按用户口径做语义选稿。

    返回挑中的条目列表（顺序即 AI 给的优先级）；未配置 Key / 调用失败 / 输出不合法
    时返回 None，由调用方退回关键词规则选稿（select_items）。
    """
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        print(f"    [{region_label}] 未配置 DEEPSEEK_API_KEY → 退回关键词规则选稿")
        return None
    if not items:
        return None

    # 去重（同标题只留一条），保持原始顺序；顺序即候选编号顺序
    cand, seen = [], set()
    for it in items:
        t = (it.get("title") or "").strip()
        if not t or t in seen:
            continue
        seen.add(t)
        cand.append(it)
    if not cand:
        return None

    def line(n, it):
        s = (it.get("summary") or "").strip().replace("\n", " ")
        s = f" — {s[:70]}" if s else ""
        return f'{n}. [{it.get("source", "?")}] {it["title"]}{s}'

    listing = "\n".join(line(n, it) for n, it in enumerate(cand, 1))
    prompt = CURATE_PROMPT.format(region=region_label, total=len(cand), cap=cap, listing=listing)

    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": 1200,
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
        print(f"    [{region_label}] DeepSeek 调用失败：{e} → 退回关键词规则选稿")
        return None

    try:
        data = json.loads(content)
    except Exception:
        m = re.search(r"\{[\s\S]*\}", content or "")
        if not m:
            print(f"    [{region_label}] AI 返回非 JSON → 退回关键词规则选稿")
            return None
        try:
            data = json.loads(m.group(0))
        except Exception:
            print(f"    [{region_label}] AI 返回 JSON 解析失败 → 退回关键词规则选稿")
            return None

    raw_items = data.get("items")
    if not isinstance(raw_items, list):
        print(f"    [{region_label}] AI 输出缺 items 列表 → 退回关键词规则选稿")
        return None

    out, used = [], set()
    for ent in raw_items:
        if not isinstance(ent, dict):
            continue
        try:
            idx = int(ent.get("i"))
        except (TypeError, ValueError):
            continue
        if not (1 <= idx <= len(cand)) or idx in used:
            continue
        title = re.sub(r"\s+", " ", str(ent.get("title") or "")).strip()
        if not title or len(title) > 60:      # 过长视为不合规，丢弃（防 AI 塞长段落）
            continue
        used.add(idx)
        out.append(dict(cand[idx - 1], title=title, ai_curated=True))
        if len(out) >= cap:
            break

    if not out:
        print(f"    [{region_label}] AI 未挑出合适条目（可能就是今天没料）→ 不写入")
        return []
    return out


def is_release_item(item) -> bool:
    # 与 _release_form 共用同一判定：发布类信号词 + 模型名/版本号命中
    return _release_form(item["title"])


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
    """清理标题，移除来源前缀与「 - 来源名」后缀。

    ⚠️ 后缀正则必须要求「-」两侧有空白（\\s+-\\s+）——否则会误伤正文里的
    连字符：如「…集成 GPT-6 Astra 推理能力」曾被截成「…集成 GPT」。
    """
    # 移除 " - 来源名" 后缀（要求两侧空白，避免误伤 GPT-6 / Claude-3 之类）
    title = re.sub(r'\s+-\s+[^-]+$', '', title)
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


def fetch_news(feeds=None, keep_english=False):
    """抓取并筛选所有 RSS 源的新闻，中文优先。

    feeds：源列表，默认 FEEDS（CI 规则版用 4 个国内媒体源）。
    keep_english：True 时英文源条目若无法翻译成中文则**保留英文原文**并标记
        lang="en"（精编流程用：OpenAI 官方 RSS 等一手源是英文，仅供判断者阅读，
        精编时由判断者译成中文标题录入；CI 规则版保持 False 以便页面全中文）。
    """
    feeds = feeds if feeds is not None else FEEDS
    items = []
    noise_cnt = 0
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=24)

    for feed_info in feeds:
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
                if is_roundup(title):
                    continue

                # 英文新闻翻译处理
                is_en = feed_info["lang"] == "en" or not contains_chinese(title)
                if is_en:
                    zh_title, zh_summary = translate_to_chinese(title, summary)
                    if zh_title:
                        title, summary = zh_title, zh_summary
                    elif keep_english:
                        # 精编流程：保留英文原文（供判断者阅读，精编时译成中文录入）
                        title = clean_title(title)
                        summary = clean_summary(summary)
                    else:
                        # 规则版：无法翻译则跳过，页面保持全中文
                        continue
                else:
                    title = clean_title(title)
                    summary = clean_summary(summary)

                # v20：侧重滤噪——贴牌泛 AI（智能汽车/消费数码/泛娱乐等）在源头滤除，
                # 只保留主流 AI 厂商/模型核心动态，避免稀释每日动态浓度
                if is_noise_weak_ai(title, summary):
                    noise_cnt += 1
                    continue

                items.append({
                    "title": title,
                    "link": link,
                    "summary": summary,
                    "source": feed_info["name"],
                    "published": published,
                    "category": classify(title),
                    "is_chinese": contains_chinese(title),
                    "lang": "zh" if contains_chinese(title) else "en",
                    "is_domestic": is_domestic(title, summary),
                    "is_key_company": is_key_company(title, summary),
                    "is_priority_form": _release_form(title),
                    "is_model_intel": is_model_intel(title, summary),
                    "is_industry": is_industry_topic(title, summary),
                })
        except Exception as e:
            print(f"  [错误] {feed_info['name']}: {e}")

    items.sort(key=lambda x: x["published"], reverse=True)
    if noise_cnt:
        print(f"  [滤噪] 边缘弱相关 AI 新闻滤除 {noise_cnt} 条（智能汽车/消费数码/泛娱乐等）")
    return items


def select_items(items, cap=6, min_score=None):
    """对单个模块桶做选稿：侧重加权 + 源均衡(cap2/源) + 国内优先 + 国内 ≥ 国外 + 总量 cap。

    min_score：v21 新增门槛。只保留侧重分 ≥ min_score 的条目（None = 不设门槛）。
    每日动态用它做「少而准」——够不上「可操作情报」的条目宁可不收，也不凑数。

    v20 侧重：先按「主流公司(+2) / 模型发布·重磅形态(+1)」降序排序（同权内新者在前），
    后续各轮均衡对已排序列表先到先得 ⇒ 高权重条目优先占满 cap、普通条目垫底。
    最终顺序仍按时间倒序 + 国内在前展示，改动只影响「谁被选中」。

    注意：v19 起动态区桶已按国内外拆开（domestic 桶全为国内、foreign 桶全为国外），
    桶内再分国内外时仅单边有内容，此处的均衡约束自动退化为「单边选满 cap」。
    ARCHIVES 三 tab 仍按混合桶调用（速报/大事记/论文含国内外条目），均衡约束继续生效。
    返回按时间倒序的最终列表（domestic 在前）。
    """
    per_source_cap = 2

    if min_score is not None:
        items = [i for i in items if _priority_score(i) >= min_score]

    # v20 加权排序：先按时间倒序（新者在前），再按侧重分稳定排序 ⇒
    # 高权重条目优先入选、同权重内仍保持「新者优先」（sorted 稳定）。
    items = sorted(items, key=lambda x: x["published"], reverse=True)
    items = sorted(items, key=lambda x: -_priority_score(x))

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


def generate_block(items, date_str, with_region=True):
    """
    生成新闻 HTML 区块。

    格式规定：
    1. 日期标题使用 dhead/ddate/dbadge 结构
    2. with_region=True：新闻分为"🇨🇳 国内"和"🌍 国外"两个区域，国内在前
       （ARCHIVES 三 tab 用，块内可能同时含国内外条目）
       with_region=False：不分 region 直接渲染 items（v19 每日动态两模块用，
       模块本身已限定单边，块内不再重复区域标签）
    3. 每条新闻使用 cat/body/h4/p/src 结构
    4. 标题必须可点击（<a> 标签）
    5. 来源必须可点击
    """
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

    if not with_region:
        # 动态区单边模块：直接平铺所有条目
        for item in items:
            lines.extend(render_item(item))
        lines.append("    </div>")
        return "\n".join(lines)

    # 按国内外分组（with_region=True，ARCHIVES 用）
    domestic = [i for i in items if i.get("is_domestic")]
    foreign = [i for i in items if not i.get("is_domestic")]

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

    marker 示例：'<!-- __DOMESTIC_INSERT__'、'<!-- __RELEASE_INSERT__'。
    防重粒度 = 区段：从本 marker 行起，到「下一个注释 marker」与「最近的 </section>」
    中更近者为止，该区间若已含 date_label（如「2026-09-09 早间更新」）则跳过——
    每日动态两模块各在一个 <section class="dyn-mod"> 内，区段被各自 </section> 精确
    截断；ARCHIVES 三 tab 无 section，靠相邻 marker 截断。两类互不污染。
    """
    path = Path("news.html")
    content = path.read_text(encoding="utf-8")
    if marker not in content:
        print(f"错误：未找到标记 {marker}，跳过 {label}")
        return False

    idx = content.find(marker)
    # 区段终点：取 idx 之后的「最近注释 marker」与「最近 </section>」中较近者
    nxt = len(content)
    for m in re.finditer(r'<!--\s*__[A-Za-z0-9_]+_INSERT__', content):
        if m.start() > idx and m.start() < nxt:
            nxt = m.start()
    end_sec = content.find("</section>", idx)
    if end_sec != -1 and end_sec < nxt:
        nxt = end_sec

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
    2. 接收国内/国外模块的代表列表（≤4 条，国内在前、国外在后，各最多 2 条）
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

    print(f"正在抓取 {date_label} 的 AI 新闻（国内源，按国内外归档）...")
    items = fetch_news()
    if not items:
        print("未找到 AI 相关新闻，跳过。")
        return

    chinese_count = sum(1 for i in items if i.get("is_chinese"))
    domestic_count = sum(1 for i in items if i.get("is_domestic"))
    key_count = sum(1 for i in items if i.get("is_key_company"))
    form_count = sum(1 for i in items if i.get("is_priority_form"))
    print(f"抓到 {len(items)} 条 AI 候选（中文 {chinese_count} 条，国内 {domestic_count} 条，"
          f"主流公司 {key_count} 条，发布/重磅形态 {form_count} 条）")

    # 按国内外归档：domestic 桶 = 国产模型/厂商相关；foreign 桶 = 海外动态
    buckets = {
        "domestic": [it for it in items if it.get("is_domestic")],
        "foreign":  [it for it in items if not it.get("is_domestic")],
    }
    for key in ("domestic", "foreign"):
        print(f"  [{key}] 候选 {len(buckets[key])} 条")

    # 每个模块独立选稿 + 插入（防重按区段）；首页代表 = 国内/国外各取前 2
    curate_mode = "DeepSeek AI 精编" if os.environ.get("DEEPSEEK_API_KEY") else "关键词规则选稿"
    print(f"选稿模式：{curate_mode}")
    any_inserted = False
    picks = []
    for marker, key, label in MODULES:
        bucket = buckets.get(key, [])
        # ① 优先 AI 语义精编（线上 CI 内完成，不依赖本地）；
        #    ② 没 Key / 调用失败 / AI 判定无料 → 退回 v21 关键词门槛选稿（≥3 分，少而准）
        ai_sel = ai_curate(bucket, label, cap=6)
        if ai_sel:
            sel, mode = ai_sel, "AI 精编"
        else:
            if ai_sel == []:
                print(f"    [{label}] AI 判定今日无够格情报，退回关键词规则兜底（保持页面不空）")
            sel, mode = select_items(bucket, cap=6, min_score=3), "规则兜底"
        if not sel:
            print(f"· {label}（{key}）今日无合适内容，跳过")
            continue
        # 动态区模块本身已限定单边（国内桶全为国内、国外桶全为国外），块内不再重复 region 标签
        block = generate_block(sel, date_label, with_region=False)
        if insert_module(block, f"<!-- {marker}", label, date_label):
            print(f"✓ news.html [{label}] 已追加 {date_label}（{len(sel)} 条 · {mode}）")
            any_inserted = True
        picks.extend(sel[:2])  # 各模块最多取 2 条代表（模块已写或已存在都取同一条，保证首页与页面一致）

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
