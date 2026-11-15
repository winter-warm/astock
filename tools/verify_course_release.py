"""Run reproducible pre-package checks; never create or bless the editorial baseline."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

from astock.course_library import catalogue, resource, validate
from astock.tutorial_release import sha256, snapshot


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--notebook-python', required=True)
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[1]
    output = project / 'output' / ('tutorial-release-' + datetime.now().strftime('%Y%m%d-%H%M%S'))
    output.mkdir(parents=True)
    current = snapshot(project)
    reports = {}

    def save(kind, value):
        path = output / (kind + '.json')
        value['snapshot_digest'] = current['digest']
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
        reports[kind] = {'report': path.relative_to(project).as_posix(), 'sha256': sha256(path)}
        print(kind + ': ' + str(value.get('passed')), flush=True)
        if value.get('passed') is not True:
            raise RuntimeError('验收失败，保留日志：' + str(path))

    def command(name, argv, env=None):
        path = output / (name + '.log')
        with path.open('w', encoding='utf-8') as log:
            result = subprocess.run(argv, cwd=project, env={**os.environ, 'PYTHONUTF8': '1', **(env or {})},
                                    stdout=log, stderr=subprocess.STDOUT, timeout=1800)
        return {'exit_code': result.returncode, 'log': path.relative_to(project).as_posix(), 'sha256': sha256(path)}

    errors = validate(require_complete=True)
    counts = {e['id']: len(re.findall(r'[\u4e00-\u9fff]', re.sub(r'```[\s\S]*?```', '', resource(e['body']).read_text(encoding='utf-8'))))
              for e in catalogue() if e['kind'] == 'course' and e.get('status') == 'published'}
    save('content', {'passed': not errors, 'errors': errors, 'lessons': len(counts), 'prose_han_characters': counts})
    static = command('control-registration', [sys.executable, 'tools/register_help_targets.py', '--check'])
    matrices = []
    for theme, scale, width, height in [('dark', '1.25', 1280, 760), ('light', '1.25', 1100, 680),
                                        ('dark', '1.5', 1100, 680), ('light', '1.5', 1280, 760)]:
        case = f'{theme}-{scale}-{width}'
        directory = output / case
        run = command(case, [sys.executable, 'tools/check_course_interface.py', '--output', str(directory),
                             '--theme', theme, '--width', str(width), '--height', str(height)],
                       {'QT_SCALE_FACTOR': '1', 'QT_SCREEN_SCALE_FACTORS': scale})
        report = json.loads((directory / 'interface-report.json').read_text(encoding='utf-8'))
        matrices.append({'case': case, **run, 'report': str((directory / 'interface-report.json').relative_to(project)),
                         'passed': report['passed'], 'surfaces': len(report['surfaces']), 'observed': len(report['observed_ids']),
                         'uncovered': report['uncovered'], 'missing_targets': report['missing_targets']})
    coverage = {'passed': static['exit_code'] == 0 and all(m['passed'] and m['exit_code'] == 0 for m in matrices),
                'static': static, 'matrices': matrices, 'uncovered': sum((m['uncovered'] for m in matrices), []),
                'missing_targets': sum((m['missing_targets'] for m in matrices), [])}
    save('interface_coverage', coverage)
    save('gui', {'passed': coverage['passed'], 'matrices': matrices, 'visual_review_required': True})
    regression = command('pytest', [sys.executable, '-m', 'pytest', '-vv', '-s', '--tb=short',
                                    '--junitxml=' + str(output / 'pytest.xml')])
    junit = output / 'pytest.xml'
    suites = ET.parse(junit).getroot().findall('testsuite') if junit.exists() else []
    total = {name: sum(int(s.attrib.get(name, 0)) for s in suites) for name in ('tests', 'failures', 'errors', 'skipped')}
    lint = command('ruff', [sys.executable, '-m', 'ruff', 'check', 'src', 'tests', 'tools'])
    save('regression', {'passed': regression['exit_code'] == 0 and lint['exit_code'] == 0 and total['tests'] > 0,
                        'junit_written': junit.exists(), **total,
                        'pytest': regression, 'lint': lint})
    notebooks = command('notebooks', [sys.executable, 'tools/check_course_notebooks.py', '--python', args.notebook_python, '--release'])
    log = (project / notebooks['log']).read_text(encoding='utf-8')
    # The checker prints the actual export path after successful execution.
    match = re.search(r'NOTEBOOK_REPORT=(.+)', log)
    detail = json.loads(Path(match.group(1).strip()).read_text(encoding='utf-8')) if match else {}
    save('notebooks', {'passed': notebooks['exit_code'] == 0 and detail.get('passed') is True
                      and len(detail.get('records', [])) == 72, 'execution': notebooks,
                       'detail': detail, 'detail_path': match.group(1).strip() if match else None})
    if snapshot(project)['digest'] != current['digest']:
        raise RuntimeError('验收期间源码或正文变化，不能使用本轮作为最终发布证据')
    (output / 'evidence-index.json').write_text(json.dumps({'snapshot_digest': current['digest'], 'evidence': reports}, indent=2), encoding='utf-8')
    print('EVIDENCE=' + str(output), flush=True)


if __name__ == '__main__':
    main()
