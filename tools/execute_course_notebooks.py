"""Run exported notebooks with this interpreter, using a private kernelspec."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import shutil
import time
import traceback

import nbformat
from nbclient import NotebookClient


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--timeout', type=int, default=180)
    args = parser.parse_args()
    root = args.directory.resolve()
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    kernels = root / '.jupyter' / 'kernels' / 'astock-course'
    kernels.mkdir(parents=True, exist_ok=True)
    spec = {'argv': [sys.executable, '-m', 'ipykernel_launcher', '-f', '{connection_file}'],
            'display_name': 'AStock CPU 课程验收', 'language': 'python'}
    (kernels / 'kernel.json').write_text(json.dumps(spec), encoding='utf-8')
    os.environ['JUPYTER_PATH'] = str(root / '.jupyter')
    os.environ['JUPYTER_RUNTIME_DIR'] = str(root / '.jupyter' / 'runtime')
    os.environ['JUPYTER_CONFIG_DIR'] = str(root / '.jupyter' / 'config')
    os.environ['IPYTHONDIR'] = str(root / '.ipython')
    os.environ['MPLCONFIGDIR'] = str(root / '.matplotlib')
    for name in ('JUPYTER_RUNTIME_DIR', 'JUPYTER_CONFIG_DIR', 'IPYTHONDIR', 'MPLCONFIGDIR'):
        Path(os.environ[name]).mkdir(parents=True, exist_ok=True)
    os.environ['MPLBACKEND'] = 'Agg'
    os.environ['PYTHONUTF8'] = '1'
    os.environ['ASTOCK_LLM_ONLINE'] = '0'
    output = root / 'executed'
    output.mkdir(exist_ok=True)
    records = []
    for file in sorted(root.glob('q*.ipynb')):
        print('启动独立内核：' + file.name, flush=True)
        started = time.monotonic()
        source = file.read_bytes()
        record = {'file': file.name, 'source_sha256': hashlib.sha256(source).hexdigest(), 'passed': False}
        try:
            value = nbformat.read(file, as_version=4)
            nbformat.validate(value)
            workspace = root / 'workspaces' / file.stem
            workspace.mkdir(parents=True, exist_ok=True)
            for directory in ('examples', 'datasets', 'images'):
                if (root / directory).is_dir():
                    shutil.copytree(root / directory, workspace / directory, dirs_exist_ok=True)
            NotebookClient(value, timeout=args.timeout, startup_timeout=30, kernel_name='astock-course',
                           resources={'metadata': {'path': str(workspace)}}, allow_errors=False).execute()
            nbformat.write(value, output / file.name)
            record['passed'] = True
            record['executed_cells'] = sum(c.cell_type == 'code' for c in value.cells)
            record['workspace'] = str(workspace)
        except Exception:
            record['error'] = traceback.format_exc()
        record['seconds'] = round(time.monotonic() - started, 3)
        records.append(record)
        print(f"{file.name}: {'通过' if record['passed'] else '失败'} ({record['seconds']}s)", flush=True)
        (root / 'execution-report.json').write_text(json.dumps({'python': sys.executable,
            'passed': all(r['passed'] for r in records), 'records': records}, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if records and all(r['passed'] for r in records) else 1


if __name__ == '__main__':
    raise SystemExit(main())
