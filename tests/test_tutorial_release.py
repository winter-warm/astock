import json
from astock.tutorial_release import sha256, snapshot, validate_baseline


def make_fixture(root):
    source = root / 'src/astock'
    source.mkdir(parents=True)
    (source / 'window.py').write_text('button = "开始"', encoding='utf-8')
    content = source / 'course_content'
    content.mkdir()
    (content / 'lesson.md').write_text('按开始执行。', encoding='utf-8')
    (root / 'docs').mkdir()
    (root / 'pyproject.toml').write_text('version = "1.0.0"', encoding='utf-8')
    current = snapshot(root)
    evidence = {}
    for kind in ('content', 'notebooks', 'interface_coverage', 'gui', 'regression', 'package'):
        path = root / 'docs' / (kind + '.json')
        path.write_text(json.dumps({'passed': True, 'snapshot_digest': current['digest'],
                                    'uncovered': [], 'missing_targets': []}), encoding='utf-8')
        evidence[kind] = {'report': str(path.relative_to(root)), 'sha256': sha256(path)}
    baseline = {'snapshot_digest': current['digest'], 'files': current['files'], 'evidence': evidence,
                'reviews': [{'verdict': 'reviewed', 'note': '测试夹具，非产品发布凭据。'}]}
    (root / 'docs/tutorial-release-baseline.json').write_text(json.dumps(baseline), encoding='utf-8')
    return baseline


def test_clean_matching_evidence_passes(tmp_path):
    make_fixture(tmp_path)
    assert validate_baseline(tmp_path, packaged=True) == []


def test_code_or_text_change_invalidates_review(tmp_path):
    make_fixture(tmp_path)
    (tmp_path / 'src/astock/window.py').write_text('button = "停止"', encoding='utf-8')
    assert any('需复核' in error for error in validate_baseline(tmp_path))
    (tmp_path / 'pyproject.toml').write_text('version = "2.0.0"', encoding='utf-8')
    assert validate_baseline(tmp_path)  # Version changes cannot bless modified behavior.


def test_old_report_or_changed_evidence_is_rejected(tmp_path):
    make_fixture(tmp_path)
    (tmp_path / 'docs/notebooks.json').write_text('{"passed": true}', encoding='utf-8')
    assert any('报告内容已变化' in error for error in validate_baseline(tmp_path))


def test_missing_baseline_is_not_silently_created(tmp_path):
    assert validate_baseline(tmp_path)
    assert not (tmp_path / 'docs/tutorial-release-baseline.json').exists()
