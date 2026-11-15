"""Launch two copies against disposable data; second must exit before smoke work."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--exe', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    root = output / 'data'
    env = {**os.environ, 'PATH': os.environ['SystemRoot'] + '\\System32;' + os.environ['SystemRoot'],
           'PYTHONPATH': '', 'ASTOCK_DATA_DIR': '', 'QT_QPA_PLATFORM': 'windows'}
    exe = str(Path(args.exe).resolve())
    first = subprocess.Popen([exe, '--learning-smoke', '--data-dir', str(root), '--screenshot', str(output / 'first.png')], env=env)
    report = {'passed': False}
    try:
        deadline = time.monotonic() + 30
        while not (root / 'workbench.sqlite3').exists():
            if first.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError('First instance did not start')
            time.sleep(.02)
        second = subprocess.run([exe, '--course-smoke', '--data-dir', str(root),
                                 '--screenshot', str(output / 'duplicate.png')], env=env, timeout=25)
        report['second_exit_code'] = second.returncode
        assert second.returncode == 0
        assert not (output / 'course-result.json').exists(), 'Second instance reached work execution'
        assert not (output / 'duplicate.png').exists()
        report['first_exit_code'] = first.wait(timeout=65)
        assert report['first_exit_code'] == 0
        learning = json.loads((output / 'learning-result.json').read_text(encoding='utf-8'))
        assert learning['passed']
        report['first_workflow_passed'] = True
        report['duplicate_did_not_execute'] = True
        report['passed'] = True
    finally:
        if first.poll() is None:
            # Only the disposable validation process tree is terminated.
            subprocess.run(['taskkill', '/PID', str(first.pid), '/T', '/F'], capture_output=True)
        (output / 'single-instance-result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(output / 'single-instance-result.json')


if __name__ == '__main__':
    main()
