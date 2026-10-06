"""免费新闻筛选：保守的标题去重，保留不同版本和不同数字的消息。"""
import html
import re
from difflib import SequenceMatcher


def normalized_title(title):
    title = html.unescape(title).lower()
    title = re.sub(r"^(独家|快讯|重磅|刚刚|最新)[：:！!，,\s]*", "", title)
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", title)


def same_event(left, right):
    a, b = normalized_title(left), normalized_title(right)
    if not a or not b:
        return False
    # 版本、日期、价格或规模不同，宁可保留，避免吞掉新的事实。
    if re.findall(r"\d+(?:\.\d+)*", left) != re.findall(r"\d+(?:\.\d+)*", right):
        return False
    entities = r'deepseek|qwen|openai|chatgpt|claude|anthropic|gemini|google|kimi|minimax|glm|mcp|腾讯|阿里|百度|字节|豆包|通义|千问|智谱|华为|混元'
    if set(re.findall(entities, a)) != set(re.findall(entities, b)):
        return False
    if a == b:
        return True
    return min(len(a), len(b)) >= 12 and SequenceMatcher(None, a, b).ratio() >= 0.82


def deduplicate(items, previous_titles=()):
    """调用方先按优先级排序；重复报道保留先出现的来源。"""
    kept, titles = [], list(previous_titles)
    for item in items:
        title = item.get("title", "")
        if any(same_event(title, old) for old in titles):
            continue
        kept.append(item)
        titles.append(title)
    return kept
