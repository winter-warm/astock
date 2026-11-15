"""Assign explicit IDs once; subsequent --check detects undocumented new constructors.

This tool creates an inventory requiring editorial review, never a completed manual.
"""
import argparse
import ast
import json
from pathlib import Path


FILES = ('account_overview.py', 'backtest_setup.py', 'backtest_workspace.py', 'catalog_ui.py',
         'model_browser.py', 'model_trading.py', 'operations_ui.py', 'qmt_workspace.py',
         'quality_ui.py', 'rule_history_ui.py', 'strategy_editor_window.py', 'window.py', 'course_ui.py',
         'help_controller.py', 'control_help.py')
CLASSES = {'QPushButton', 'QToolButton', 'QComboBox', 'QLineEdit', 'QSpinBox', 'QDoubleSpinBox',
           'QDateEdit', 'QCheckBox', 'QRadioButton', 'QTextBrowser', 'QPlainTextEdit', 'QTableWidget',
           'QTableView', 'QTreeWidget', 'QListWidget', 'QSlider', 'QTabWidget', 'QDialogButtonBox',
           'RecordTable', 'CodeEditor', 'PlotWidget', 'PriceChart', 'EquityChart'}


def inspect(path):
    text = path.read_text(encoding='utf-8')
    tree = ast.parse(text)
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else ''
        is_widget = ((isinstance(node.func, ast.Name) and name in CLASSES | {'button', 'table'})
                     or (isinstance(node.func, ast.Attribute) and name in CLASSES))
        is_action = name == 'addAction' and bool(node.args) and isinstance(node.args[0], (ast.Constant, ast.Name))
        if not (is_widget or is_action):
            continue
        parent = parents.get(node)
        wrapped = isinstance(parent, ast.Call) and isinstance(parent.func, ast.Name) and parent.func.id == 'help_target'
        chain, current = [], parent
        while current:
            if isinstance(current, (ast.ClassDef, ast.FunctionDef)):
                chain.append(current.name)
            current = parents.get(current)
        context = '.'.join([path.stem] + list(reversed(chain)))
        assignment = parents.get(parent) if wrapped else parent
        target = ''
        if isinstance(assignment, ast.Assign):
            target = ast.unparse(assignment.targets[0]).removeprefix('self.')
        label = ''
        if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
            label = node.args[0].value
        identity = parent.args[1].value if wrapped else None
        found.append({'node': node, 'id': identity, 'context': context, 'target': target, 'label': label,
                      'constructor': name, 'expression': ast.get_source_segment(text, node), 'line': node.lineno})
    return text, tree, found


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[1]
    root = project / 'src/astock'
    inventory_file = root / 'course_content/interface_controls.json'
    existing = {r['id']: r for r in json.loads(inventory_file.read_text(encoding='utf-8'))} if inventory_file.exists() else {}
    inventory, missing = [], []
    files = sorted(set(FILES) | {p.name for p in root.glob('*.py')
                                if p.name != 'ui_components.py' and not p.stem.endswith('_validation')})
    for filename in files:
        path = root / filename
        text, tree, controls = inspect(path)
        edits = []
        offsets = [0]
        for line in text.splitlines(keepends=True):
            offsets.append(offsets[-1] + len(line.encode('utf-8')))
        used = {row['id'] for row in controls if row['id']}
        for row in controls:
            node = row.pop('node')
            if not row['id']:
                base = row['context'] + '.' + (row['target'] or row['constructor'])
                identity, index = base, 1
                while identity in used:
                    index += 1
                    identity = base + str(index)
                used.add(identity)
                row['id'] = identity
                missing.append(identity)
                start = offsets[node.lineno - 1] + node.col_offset
                end = offsets[node.end_lineno - 1] + node.end_col_offset
                edits.append((start, 'help_target('))
                edits.append((end, ', ' + repr(identity) + ')'))
            old = existing.get(row['id'], {})
            inventory.append({**row, 'source': 'src/astock/' + filename,
                'title': old.get('title', ''),
                'explanation': old.get('explanation', ''), 'steps': old.get('steps', ''),
                'unavailable': old.get('unavailable', ''), 'reviewed': old.get('reviewed', False)})
        if args.apply and edits:
            encoded = text.encode('utf-8')
            for at, value in sorted(edits, key=lambda e: e[0], reverse=True):
                encoded = encoded[:at] + value.encode('utf-8') + encoded[at:]
            updated = encoded.decode('utf-8')
            if 'from astock.help_registry import help_target' not in text:
                imports = [n for n in tree.body if isinstance(n, ast.ImportFrom) and n.module == '__future__']
                doc = tree.body[0] if tree.body and isinstance(tree.body[0], ast.Expr) and isinstance(tree.body[0].value, ast.Constant) and isinstance(tree.body[0].value.value, str) else None
                position = offsets[imports[-1].end_lineno] if imports else offsets[doc.end_lineno] if doc else 0
                data = updated.encode('utf-8')
                updated = (data[:position] + b'from astock.help_registry import help_target\n' + data[position:]).decode('utf-8')
            compile(updated, filename, 'exec')
            path.write_text(updated, encoding='utf-8')
    if args.apply:
        inventory_file.write_text(json.dumps(inventory, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'controls={len(inventory)} unregistered={len(missing)}')
    if args.check:
        for identity in missing:
            print(identity)
        return bool(missing)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
