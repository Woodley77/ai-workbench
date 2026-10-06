"""免费更新共用的状态、来源、时间记录和历史保留工具。"""
from pathlib import Path
from datetime import datetime, timedelta, timezone
import hashlib
import html
import json
import re
from urllib.parse import urlsplit

CST = timezone(timedelta(hours=8))
OFFICIAL_FEEDS = [
    {'url': 'https://openai.com/news/rss.xml', 'name': 'OpenAI 官方（英文原文）', 'lang': 'en', 'official': True},
    {'url': 'https://huggingface.co/blog/feed.xml', 'name': 'Hugging Face 平台博客（英文原文）', 'lang': 'en', 'official': True},
]
RETENTION_DAYS = 90
MAX_BLOCKS = 60  # 每个动态栏目；超过范围的内容先归档再移出页面。

def now_iso():
    return datetime.now(CST).isoformat(timespec='seconds')

def read_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return default

def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)

def safe_url(url):
    try:
        parts = urlsplit(str(url))
        return parts.scheme.lower() in ('http', 'https') and bool(parts.hostname) and not parts.username and not parts.password
    except ValueError:
        return False

def priority(item):
    return (3 if item.get('official') else 0, item.get('published') is not None, item.get('published') or datetime.min.replace(tzinfo=CST))

def headline_links(root):
    links = set()
    for name in ('news.html','models.html','agents.html','wiki-skills.html','wiki-mcp.html'):
        path = Path(root)/name
        if path.exists():
            links.update(html.unescape(x) for x in re.findall(r'<h4><a href="([^"]+)"',path.read_text(encoding='utf-8')))
    return links

def record_run(root, channel, started, feeds, before, error=None):
    path = Path(root)/'data/site-status.json'
    state = read_json(path, {'channels':{}})
    channels = state.setdefault('channels',{})
    previous = channels.get(channel,{})
    added = len(headline_links(root)-before)
    results = list(feeds.values())
    successes = sum(row['ok'] for row in results)
    partial = successes < len(results)
    stamp = now_iso()
    row = dict(previous, last_attempt=stamp, started_at=started, sources=results,
               source_successes=successes, source_total=len(results), new_links=added,
               result='failed' if error else ('partial' if partial else ('updated' if added else 'no_change')))
    if not error:
        row['last_success'] = stamp
    if added:
        row['last_new_content'] = stamp
    if error:
        row['error'] = '更新失败，请查看运行日志'  # 不把请求异常、令牌或响应正文写进公开数据。
    else:
        row.pop('error',None)
    channels[channel] = row
    state['as_of'] = stamp
    write_json(path,state)

def seen_records(value):
    stamp = now_iso()
    if isinstance(value,list):
        return {url:{'processed_at':stamp,'legacy':True} for url in value if isinstance(url,str)}
    return value if isinstance(value,dict) else {}

def remember(records, urls, limit=2000):
    stamp = now_iso()
    records = dict(records)
    for url in urls:
        records[url] = {'processed_at':stamp}
    cutoff = (datetime.now(CST)-timedelta(days=RETENTION_DAYS)).isoformat()
    records = {url:row for url,row in records.items() if isinstance(row,dict) and row.get('processed_at','') >= cutoff}
    return dict(sorted(records.items(),key=lambda pair:(pair[1]['processed_at'],not pair[1].get('legacy',False)),reverse=True)[:limit])

def archive_old_blocks(root):
    """逐个栏目保留最近 90 天/60 块；先写入可检索 JSONL，随后修改页面。"""
    root = Path(root)
    archive = root/'data/news-archive.jsonl'
    known = set()
    if archive.exists():
        for line in archive.read_text(encoding='utf-8').splitlines():
            known.add(json.loads(line)['id'])  # 损坏的历史文件必须报错，不能静默丢掉历史。
    cutoff = (datetime.now(CST)-timedelta(days=RETENTION_DAYS)).date().isoformat()
    pending, updates = [], {}
    for page in ('news.html','models.html','agents.html','wiki-skills.html','wiki-mcp.html'):
        path = root/page
        if not path.exists():continue
        text = path.read_text(encoding='utf-8')
        removals, counts = [], {}
        markers = list(re.finditer(r'<!--\s*(__[A-Z0-9_]+_INSERT__)',text))
        for start in re.finditer(r'<div\s+class="(?:news-day|verify-day)"[^>]*>',text):
            candidates = [m for m in markers if m.start()<start.start()]
            if not candidates:continue
            marker = candidates[-1].group(1)
            depth, end = 0, None
            for token in re.finditer(r'</?div\b[^>]*>',text[start.start():]):
                depth += -1 if token.group().startswith('</') else 1
                if depth==0:
                    end = start.start()+token.end();break
            if end is None:raise ValueError('动态区 HTML 不完整，停止归档')
            block = text[start.start():end]
            found = re.search(r'class="ddate">(\d{4}-\d{2}-\d{2})',block)
            day = found.group(1) if found else None
            counts[marker] = counts.get(marker,0)+1
            if (day and day<cutoff) or counts[marker]>MAX_BLOCKS:
                digest = hashlib.sha256((page+marker+block).encode()).hexdigest()
                if digest not in known:
                    pending.append({'id':digest,'page':page,'section':marker,'date':day,'archived_at':now_iso(),'html':block})
                    known.add(digest)
                removals.append((start.start(),end))
        for start,end in reversed(removals):text=text[:start]+text[end:]
        if removals:updates[path]=text
    if pending:
        archive.parent.mkdir(parents=True,exist_ok=True)
        existing = archive.read_text(encoding='utf-8') if archive.exists() else ''
        temporary = archive.with_suffix('.jsonl.tmp')
        temporary.write_text(existing+''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in pending),encoding='utf-8')
        temporary.replace(archive)
    for path,text in updates.items():path.write_text(text,encoding='utf-8')
    return len(pending)
