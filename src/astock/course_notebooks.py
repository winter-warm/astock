"""Export the exact published lesson sources into independently writable notebooks."""
from pathlib import Path
import hashlib
import json
import re
import shutil
import uuid

from astock.course_library import ROOT, article, catalogue, resource


def notebook(entry):
    raw = resource(entry['body']).read_text(encoding='utf-8')
    examples = {example['id']: example for example in entry.get('examples', [])}
    cells = []
    pieces = re.split(r'(\{\{code:[^}]+\}\})', raw)
    for piece in pieces:
        if not piece.strip():
            continue
        match = re.fullmatch(r'\{\{code:([^}]+)\}\}', piece)
        if match:
            example = examples[match.group(1)]
            code = resource(example['file']).read_text(encoding='utf-8')
            cell = dict(cell_type='code', source=code, execution_count=None, outputs=[],
                        metadata={'astock_example_id': example['id'],
                                  'source_sha256': hashlib.sha256(code.encode('utf-8')).hexdigest(),
                                  'environment': example.get('environment', 'lab')})
            if example.get('environment') == 'strategy':
                cell = dict(cell_type='markdown',
                            source='此段在 AStock 策略编辑器执行，Notebook 中仅阅读。\n\n```python\n' + code + '\n```',
                            metadata=cell['metadata'])
        else:
            cell = dict(cell_type='markdown', source=piece, metadata={})
        cell['id'] = hashlib.sha256(f"{entry['id']}:{len(cells)}".encode()).hexdigest()[:12]
        cells.append(cell)
    return dict(nbformat=4, nbformat_minor=5, cells=cells, metadata={
        'kernelspec': {'display_name': 'Python 3 (课程环境)', 'language': 'python', 'name': 'python3'},
        'language_info': {'name': 'python', 'version': '3.12'},
        'astock': {'lesson_id': entry['id'], 'content_version': entry['version'],
                   'content_sha256': hashlib.sha256(article(entry).encode('utf-8')).hexdigest(),
                   'data_notice': '内置样本为合成教学数据；外部执行不自动计为软件实作通过。'}})


def export_notebooks(destination, entries=None):
    """Never overwrite user notebooks; every export owns a fresh directory."""
    destination = Path(destination)
    entries = entries if entries is not None else [e for e in catalogue()
        if e['kind'] == 'course' and e.get('status') == 'published']
    if any(e.get('status') != 'published' for e in entries):
        raise ValueError('尚未编写的课程不能导出为正式 Notebook')
    target = destination / ('AStock课程-' + uuid.uuid4().hex[:12])
    target.mkdir(parents=True, exist_ok=False)
    for path in (ROOT / 'notebook_environment').iterdir():
        if path.is_file():
            shutil.copy2(path, target / path.name)
    shutil.copytree(ROOT / 'examples', target / 'examples')
    for directory in ('images', 'datasets'):
        if (ROOT / directory).exists():
            shutil.copytree(ROOT / directory, target / directory)
    manifest = []
    for entry in entries:
        value = notebook(entry)
        name = entry['id'] + '.ipynb'
        (target / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
        manifest.append({'id': entry['id'], 'title': entry['title'], 'file': name,
                         'version': entry['version'], 'sha256': value['metadata']['astock']['content_sha256']})
    (target / '课程清单.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    return target
