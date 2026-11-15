"""Export and execute all published courses; release requires every planned course."""
import argparse
from pathlib import Path
import subprocess
import sys

from astock.course_library import validate
from astock.course_notebooks import export_notebooks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--python', type=Path, required=True, help='独立 Notebook 环境的 Python')
    parser.add_argument('--output', type=Path, default=Path('output/notebook-check'))
    parser.add_argument('--release', action='store_true')
    args = parser.parse_args()
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    errors = validate(require_complete=args.release)
    if errors:
        print('\n'.join(errors))
        return 1
    target = export_notebooks(args.output)
    print('验收目录：' + str(target), flush=True)
    code = subprocess.call([str(args.python.resolve()), str(Path(__file__).with_name('execute_course_notebooks.py')),
                            str(target.resolve())])
    print('NOTEBOOK_REPORT=' + str((target / 'execution-report.json').resolve()), flush=True)
    return code


if __name__ == '__main__':
    raise SystemExit(main())
