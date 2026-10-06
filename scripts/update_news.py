#!/usr/bin/env python3
"""RSS 新闻更新：按国内外筛选、归档，联动首页。

默认保留中文标题、摘要和可点击来源；仅模型名等专有名词允许英文。
始终使用免费规则筛选，不读取 API 密钥，不调用模型接口；有新候选才写入。
精编工具 fetch_daily.py / apply_daily.py 复用本文件的抓取与渲染接口。
"""

import feedparser
import html
import json
import os
import re
import urllib.request
import argparse
from news_rules import deduplicate
from maintenance import OFFICIAL_FEEDS, safe_url, priority, now_iso, headline_links, record_run, read_json, write_json, seen_records, remember, archive_old_blocks
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
FEEDS += OFFICIAL_FEEDS
FEED_RESULTS = {}

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


# 免费规则选稿与跨天防重；不读取密钥，不调用模型接口。
def recent_titles(limit=80):
    """读 news.html 中已收录的标题（页内新块在前 ⇒ 大致新→旧），用于跨天防重。

    动态区新块插在 marker 行之后，所以标题顺序天然是「新→旧」。返回去重列表。
    """
    path = Path("news.html")
    if not path.exists():
        return []
    try:
        content = path.read_text(encoding="utf-8")
    except Exception:
        return []
    out = []
    for m in re.finditer(r'<h4><a[^>]*>([^<]+)</a></h4>', content):
        t = html.unescape(m.group(1)).strip()
        if t and t not in out:
            out.append(t)
        if len(out) >= limit:
            break
    return out




def is_release_item(item) -> bool:
    return classify(item['title']) == '模型发布'



def is_milestone_item(item) -> bool:
    return classify(item['title']) == '行业动态'



def is_paper_item(item) -> bool:
    t = item['title'].lower()
    return any(k in t for k in ['论文','arxiv','技术报告','系统卡','预印本','研究团队','研究发现','paper','学术'])



def archive_for(key: str) -> str:
    """返回归档 marker 全前缀（含注释）。"""
    for mk, k, _label, _cap, _fn in ARCHIVES:
        if k == key:
            return f"<!-- {mk}"
    raise ValueError(key)


def classify(title: str) -> str:
    """以明确事件类型分类；论文/评测不再被泛化的模型关键词抢占。"""
    t = title.lower()
    if is_unconfirmed(title):
        return '其他'
    if any(k in t for k in ['论文','arxiv','技术报告','系统卡','预印本','研究团队','研究发现','paper']):
        return '评测与研究'
    if any(k in t for k in ['定价','调价','价格','降价','涨价','计费','额度','限免','免费开放','订阅','pricing','price cut','rate limit']):
        return '价格与额度'
    if any(k in t for k in ['论文','arxiv','技术报告','系统卡','预印本','研究团队','研究发现','paper','benchmark','基准','评测','跑分','实测','测评']):
        return '评测与研究'
    if any(k in t for k in ['agent','智能体','工作台','工作流','客户端','桌面端','harness','manus','插件','skill','mcp','claude code','codex','copilot','工具','应用','浏览器','cli','ide','sdk']):
        return '工具与智能体'
    if _release_form(title) or any(k in t for k in ['模型发布','model release','introducing gpt','introducing claude']):
        return '模型发布'
    if any(k in t for k in MILESTONE_KW):
        return '行业动态'
    return '其他'


def is_unconfirmed(title):
    return bool(re.search(r'泄露|爆料|传闻|疑似|据传', title))



# 分类标签 → CSS 类名映射
CAT_CSS = {
    '模型发布':'c-model', '价格与额度':'c-event', '工具与智能体':'c-news',
    '评测与研究':'c-paper', '行业动态':'c-event', '其他':'c-news',
    "模型": "c-model",
    "热点": "c-news",
    "行业": "c-event",
    "论文": "c-paper",
}


def is_domestic(title: str, summary: str = "") -> bool:
    """判断新闻是否为国内新闻（中国企业和产品相关）。"""
    # 摘要常会顺带提到竞品，归属应以标题里的事件主体为准。
    return any(kw in title.lower() for kw in DOMESTIC_KW)


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
    text = re.sub(r'(?:点击查看原文|阅读原文|点击进入原文|查看更多)[>＞…\s]*$', '', text).strip()
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
    unique_feeds = {}
    for row in feeds:
        unique_feeds.setdefault(row['url'], row)
    feeds = list(unique_feeds.values())
    items = []
    noise_cnt = 0
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=48)
    successful_feeds = 0
    FEED_RESULTS.clear()

    for feed_info in feeds:
        FEED_RESULTS[feed_info['url']] = {'name':feed_info['name'],'url':feed_info['url'],'ok':False}
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
            successful_feeds += 1
            FEED_RESULTS[feed_info['url']]['ok'] = True
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
                published_known = published is not None
                if published is None:
                    published = now

                if published < cutoff:
                    continue

                title = entry.get("title", "").strip()
                link = entry.get("link", "").strip()
                summary = entry.get("summary", "")
                if not title or not safe_url(link):
                    continue
                if not is_ai_related(title, summary):
                    continue
                if is_roundup(title):
                    continue
                if is_unconfirmed(title):
                    continue

                # 英文新闻翻译处理
                is_en = feed_info["lang"] == "en" or not contains_chinese(title)
                if is_en and feed_info.get("official"):
                    # 官方英文原文保持原意，不经过关键词替换式翻译。
                    title = clean_title(title)
                    summary = clean_summary(summary)
                elif is_en:
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
                    "published_known": published_known,
                    "official": bool(feed_info.get("official")),
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

    print(f"  RSS 成功 {successful_feeds}/{len(feeds)} 个；时间窗 48 小时")
    if not successful_feeds:
        raise RuntimeError("全部 RSS 源抓取失败，不能认定为今天无新闻")
    items.sort(key=priority, reverse=True)
    items = deduplicate(items)
    if noise_cnt:
        print(f"  [滤噪] 边缘弱相关 AI 新闻滤除 {noise_cnt} 条（智能汽车/消费数码/泛娱乐等）")
    return items


def select_items(items, cap=6, min_score=None):
    """按事件价值、官方来源与时间排序；限制单一来源，优先覆盖不同类别。"""
    def score(item):
        return _priority_score(item) + (3 if item.get('official') else 0)
    pool = [item for item in items if min_score is None or score(item)>=min_score]
    pool.sort(key=lambda item:(score(item),item['published']),reverse=True)
    selected, sources, categories = [], {}, {}
    for category_limit in (2, None):
        for item in pool:
            if len(selected)>=cap:break
            if item in selected or sources.get(item['source'],0)>=2:continue
            if category_limit and categories.get(item['category'],0)>=category_limit:continue
            selected.append(item)
            sources[item['source']] = sources.get(item['source'],0)+1
            categories[item['category']] = categories.get(item['category'],0)+1
    return sorted(selected,key=lambda item:(bool(item.get('is_domestic')),item['published']),reverse=True)



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
        link = html.escape(item["link"], quote=True) if safe_url(item["link"]) else '#'
        source = html.escape(item["source"])
        date = item['published'].strftime('%Y-%m-%d %H:%M UTC') if item.get('published_known') else '原文日期未提供'
        source += ' · ' + date + (' · 官方原文' if item.get('official') else ' · 媒体报道')
        return [
            '      <div class="news-item">',
            f'        <span class="cat {cat_css}">{html.escape(item["category"])}</span>',
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


def _find_section(content, marker):
    """从 marker 起圈出它的「区段」[idx, nxt)。找不到 marker 返回 None。"""
    idx = content.find(marker)
    if idx == -1:
        return None
    # 区段终点：取 idx 之后的「最近注释 marker」与「最近 </section>」中较近者
    nxt = len(content)
    for m in re.finditer(r'<!--\s*__[A-Za-z0-9_]+_INSERT__', content):
        if m.start() > idx and m.start() < nxt:
            nxt = m.start()
    end_sec = content.find("</section>", idx)
    if end_sec != -1 and end_sec < nxt:
        nxt = end_sec
    return idx, nxt


def module_has_date(marker, date_label, content=None):
    """只读判断：marker 区段内是否已含 date_label。找不到 marker / 文件 → False。

    同日已有区块时使用补充标签，插入函数仍按区段防止重复写入。
    """
    if content is None:
        content = Path("news.html").read_text(encoding="utf-8")
    span = _find_section(content, marker)
    if span is None:
        return False
    idx, nxt = span
    return f'<span class="ddate">{date_label}</span>' in content[idx:nxt]


def insert_module(block, marker, label, date_label):
    """把 block 插入 news.html 指定 marker 注释行之后。

    marker 示例：'<!-- __DOMESTIC_INSERT__'、'<!-- __RELEASE_INSERT__'。
    防重粒度 = 区段：从本 marker 行起，到「下一个注释 marker」与「最近的 </section>」
    中更近者为止，该区间若已含 date_label（如「2026-09-09 早间更新」）则跳过——
    每日动态两模块各在一个 <section class="dyn-mod"> 内，区段被各自 </section> 精确
    截断；ARCHIVES 三 tab 无 section，靠相邻 marker 截断。两类互不污染。

    判重与 module_has_date 共用同一口径，避免两处漂移。
    """
    path = Path("news.html")
    content = path.read_text(encoding="utf-8")
    if marker not in content:
        print(f"错误：未找到标记 {marker}，跳过 {label}")
        return False

    if module_has_date(marker, date_label, content):
        print(f"· {label} {date_label} 已存在，跳过（防重）")
        return False

    # 在 marker 所在行的行尾之后插入 block
    idx = content.find(marker)
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
            f'<a href="{html.escape(item["link"], quote=True) if safe_url(item["link"]) else "#"}" target="_blank" rel="noopener">{title}</a></li>'
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
    """入口：显式关闭 AI；错误交由工作流报告并继续其它更新步骤。"""
    parser = argparse.ArgumentParser()
    parser.add_argument('--no-ai', action='store_true', help='关闭 AI，免费规则筛选')
    parser.parse_args()  # --no-ai 保留为兼容参数；无参数也只走免费规则。
    root = Path.cwd()
    before = headline_links(root)
    started = now_iso()
    try:
        _main_inner()
        archive_old_blocks(root)
    except Exception:
        record_run(root, 'news', started, FEED_RESULTS, before, error=True)
        raise
    record_run(root, 'news', started, FEED_RESULTS, before)


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
    print("选稿模式：免费关键词规则（不支持付费 API）")
    # 跨天防重：规则侧直接剔除页面上已收录过的标题。
    avoid = recent_titles(limit=80)
    state_path = Path('data/news-seen.json')
    seen = seen_records(read_json(state_path, {}))
    seen_urls = set(seen)
    # 页面历史链接也算已处理；状态文件记录曾被筛掉的候选，避免补班重复处理。
    existing_urls = set(re.findall(r'<h4><a href="([^"]+)"', Path('news.html').read_text(encoding='utf-8')))
    if avoid:
        print(f"  跨天防重参考：页面已有 {len(avoid)} 条历史标题")
    any_inserted = False
    picks = []
    processed_urls = set()
    for marker, key, label in MODULES:
        bucket = [it for it in buckets.get(key, [])
                  if it.get('link') not in seen_urls and it.get('link') not in existing_urls]
        if not bucket:
            print(f"· {label} 无新候选，跳过")
            continue
        pool = deduplicate(bucket, avoid)
        sel, mode = select_items(pool, cap=6, min_score=3), "免费规则"
        if not sel:
            processed_urls.update(it['link'] for it in bucket)
            print(f"· {label}（{key}）今日无合适内容，跳过")
            continue
        # 审计日志：打印实际选中的条目（即使后面因防重跳过写入，也能在 CI 日志里看到规则的选择）
        for it in sel:
            print(f"    · [{mode}] {it['title'][:64]}")
        # 动态区模块本身已限定单边（国内桶全为国内、国外桶全为国外），块内不再重复 region 标签
        label_for_block = date_label
        if module_has_date(f"<!-- {marker}", date_label):
            label_for_block = f"{date_str} {period}补充 {now_bj:%H:%M}"
        block = generate_block(sel, label_for_block, with_region=False)
        if insert_module(block, f"<!-- {marker}", label, label_for_block):
            print(f"✓ news.html [{label}] 已追加 {label_for_block}（{len(sel)} 条 · {mode}）")
            any_inserted = True
            existing_urls.update(it['link'] for it in sel)
            processed_urls.update(it['link'] for it in bucket)
        picks.extend(sel[:2])  # 各模块最多取 2 条代表（模块已写或已存在都取同一条，保证首页与页面一致）

    state_path.parent.mkdir(exist_ok=True)
    write_json(state_path, remember(seen, processed_urls))

    # 三个归档区（速报/大事记/论文）：有命中才更新，无命中跳过
    archive_fns = {"release": is_release_item, "milestone": is_milestone_item, "paper": is_paper_item}
    for mk, key, label, cap, fn_name in ARCHIVES:
        fn = archive_fns[key]
        # 学术优先，其次模型发布，最后行业；每条只进入一个专项归档。
        def destination(it):
            if is_paper_item(it): return 'paper'
            if is_release_item(it): return 'release'
            if is_milestone_item(it): return 'milestone'
            return None
        cand = [it for it in items if destination(it) == key]
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
        archive_page = Path('news.html').read_text(encoding='utf-8')
        span = _find_section(archive_page, f'<!-- {mk}')
        archive_titles = []
        if span:
            archive_titles = [html.unescape(re.sub(r'<[^>]+>', '', title)) for title in
                              re.findall(r'<h4><a[^>]*>(.*?)</a>', archive_page[span[0]:span[1]], re.DOTALL)]
        uniq = deduplicate(uniq, archive_titles)
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
