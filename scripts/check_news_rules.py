"""基于站内历史标题的分类回归；只检查规则，不验证报道事实。"""
from pathlib import Path
import json
from update_news import classify, is_unconfirmed
from news_rules import same_event

def main():
    cases = json.loads((Path(__file__).resolve().parent.parent/'data/news-rule-cases.json').read_text(encoding='utf-8'))
    failures = []
    for case in cases:
        if classify(case['title']) != case['category'] or (not is_unconfirmed(case['title'])) != case['eligible']:
            failures.append(case['title'])
    assert same_event('DeepSeek 发布 V4.1 模型','DeepSeek 发布 V4.1 模型')
    assert not same_event('DeepSeek 发布 V4.1 模型','DeepSeek 发布 V4.2 模型')
    if failures:raise AssertionError('分类回归未通过：'+str(failures))
    print(f'历史标题分类与传闻排除：{len(cases)}/{len(cases)}；相同事件/不同版本去重通过')

if __name__=='__main__':main()
