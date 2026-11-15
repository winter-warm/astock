"""Evidence-bound tutorial release checks, independent of Git availability."""
import hashlib
import json
from pathlib import Path


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def snapshot(project):
    project = Path(project).resolve()
    paths = set((project / 'src' / 'astock').rglob('*.py'))
    paths.update(p for p in (project / 'src' / 'astock' / 'course_content').rglob('*')
                 if p.is_file() and '__pycache__' not in p.parts)
    paths.update((project / 'tests').glob('test_*.py'))
    paths.update((project / 'tools').glob('*.py'))
    paths.update(project / name for name in ('pyproject.toml', 'uv.lock', 'AStock.spec',
        'Build-AStock.ps1', 'tools/Test-Release.ps1', 'docs/DATA_FORMAT.md', 'README.md', 'docs/TUTORIAL_MAINTENANCE.md'))
    hashes = {path.relative_to(project).as_posix(): sha256(path) for path in sorted(paths) if path.is_file()}
    encoded = json.dumps(hashes, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return {'files': hashes, 'digest': hashlib.sha256(encoded).hexdigest()}


def validate_baseline(project, *, packaged=False):
    project = Path(project).resolve()
    baseline_path = project / 'docs' / 'tutorial-release-baseline.json'
    if not baseline_path.exists():
        return ['尚无教程发布复核基线；不能仅修改版本号声明教程已适配。']
    try:
        baseline = json.loads(baseline_path.read_text(encoding='utf-8'))
        current = snapshot(project)
        errors = []
        if baseline.get('snapshot_digest') != current['digest']:
            previous = baseline.get('files', {})
            changed = sorted(name for name in set(previous) | set(current['files'])
                             if previous.get(name) != current['files'].get(name))
            errors.append('实现、课程或验收条件变化，需复核：' + ', '.join(changed[:20]))
        reviews = baseline.get('reviews', [])
        if not reviews or any(not r.get('note', '').strip() or r.get('verdict') != 'reviewed' for r in reviews):
            errors.append('缺少明确的内容/操作语义复核说明。')
        required = {'content', 'notebooks', 'interface_coverage', 'gui', 'regression'}
        if packaged:
            required.add('package')
        evidence = baseline.get('evidence', {})
        for kind in sorted(required):
            record = evidence.get(kind, {})
            relative = record.get('report', '')
            path = (project / relative).resolve()
            if not relative or not path.is_relative_to(project) or not path.is_file():
                errors.append('缺少验收报告：' + kind)
                continue
            if sha256(path) != record.get('sha256'):
                errors.append('验收报告内容已变化：' + kind)
                continue
            report = json.loads(path.read_text(encoding='utf-8'))
            if report.get('passed') is not True or report.get('snapshot_digest') != current['digest']:
                errors.append('验收未通过或不对应当前源码及正文：' + kind)
            if kind == 'interface_coverage' and (report.get('uncovered') or report.get('missing_targets')):
                errors.append('界面存在未覆盖或失效目标。')
        return errors
    except (ValueError, OSError, TypeError, KeyError) as error:
        return ['教程发布证据无法读取：' + str(error)]
