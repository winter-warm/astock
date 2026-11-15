"""Versioned, offline learning resources. Draft entries never count as published lessons."""
from pathlib import Path
import hashlib
import json
import re


ROOT = Path(__file__).with_name('course_content')


def catalogue():
    return json.loads((ROOT / 'catalogue.json').read_text(encoding='utf-8'))


def resource(relative):
    path = (ROOT / relative).resolve()
    if not path.is_relative_to(ROOT.resolve()):
        raise ValueError('课程资源路径越界')
    return path


def article(entry):
    text = resource(entry['body']).read_text(encoding='utf-8')
    for example in entry.get('examples', []):
        code = resource(example['file']).read_text(encoding='utf-8')
        text = text.replace('{{code:' + example['id'] + '}}', '```python\n' + code.rstrip() + '\n```')
    return text


def digest(entry):
    value = article(entry) + json.dumps(entry.get('check', {}), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def validate(require_complete=False):
    entries = catalogue()
    errors = []
    identities = set()
    courses = [e for e in entries if e['kind'] == 'course']
    for entry in entries:
        if entry['id'] in identities:
            errors.append('重复 ID: ' + entry['id'])
        identities.add(entry['id'])
        if entry.get('status') != 'published':
            if require_complete:
                errors.append('未完成正文: ' + entry['id'])
            continue
        try:
            body = article(entry)
            if '{{code:' in body:
                errors.append('代码引用未解析: ' + entry['id'])
            if not body.strip():
                errors.append('空正文: ' + entry['id'])
            if require_complete and entry['kind'] == 'course':
                raw = resource(entry['body']).read_text(encoding='utf-8')
                prose = re.sub(r'```[\s\S]*?```', '', raw)
                minimum = 650 if int(entry['id'][1:]) <= 6 else 2000
                if len(re.findall(r'[\u4e00-\u9fff]', prose)) < minimum:
                    errors.append('正文深度不足（不含代码）: ' + entry['id'])
                check = entry.get('check', {})
                if not check.get('question') or not check.get('answers') or not check.get('explanation'):
                    errors.append('缺少可核验知识题: ' + entry['id'])
                if not entry.get('examples'):
                    errors.append('缺少同源可运行示例: ' + entry['id'])
                for example in entry.get('examples', []):
                    if example.get('environment', 'lab') not in ('lab', 'strategy', 'notebook'):
                        errors.append('示例运行环境无效: ' + example['id'])
        except (KeyError, OSError, ValueError) as error:
            errors.append(f"{entry['id']}: {error}")
    if len(courses) != 72:
        errors.append(f'课程目录应为 72 课，实际 {len(courses)}')
    if {e['id'] for e in courses} != {f'q{i:02d}' for i in range(1, 73)}:
        errors.append('课程 ID 必须完整覆盖 q01–q72')
    return errors
