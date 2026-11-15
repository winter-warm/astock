"""Merge independently authored, contiguous course chains without replacing manuals."""
import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--partial', action='store_true', help='允许仍在编写的分组缺席；不可用于发布验收')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1] / 'src/astock/course_content'
    destination = root / 'catalogue.json'
    entries = json.loads(destination.read_text(encoding='utf-8'))
    replacements = {}
    for name, start, end in [('foundations', 1, 28), ('strategies', 29, 48), ('advanced', 49, 72)]:
        path = root / ('catalogue-' + name + '.json')
        if not path.exists() and args.partial:
            continue
        rows = json.loads(path.read_text(encoding='utf-8'))
        expected = {f'q{i:02d}' for i in range(start, end + 1)}
        if {r['id'] for r in rows} != expected or len(rows) != len(expected):
            raise ValueError('目录分组 ID 不完整或越界：' + name)
        if any(row.get('kind') != 'course' for row in rows):
            raise ValueError('课程分组不可替换操作手册')
        replacements.update({r['id']: r for r in rows})
    result = [replacements.get(entry['id'], entry) for entry in entries]
    temporary = destination.with_suffix('.tmp')
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(destination)
    print(f'合并课程 {len(replacements)} / 72')


if __name__ == '__main__':
    main()
