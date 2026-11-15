"""Render reviewed control records into searchable offline manual articles."""
import json
from pathlib import Path


AREAS = {
 'task_guide': '历史任务核对资料', 'onboarding': '使用教程', 'app_reset': '初始化应用',
 'account_overview': '账户与记录', 'backtest_setup': '回测设置',
 'backtest_workspace': '回测总览', 'catalog_ui': '证券目录', 'model_browser': '模板与已存策略',
 'model_trading': '模拟交易', 'operations_ui': '报告、对比与录制恢复', 'qmt_workspace': '数据中心',
 'quality_ui': '数据缺口检查', 'rule_history_ui': '历史证券规则',
 'strategy_editor_window': '写策略', 'window': '主工作台',
 'course_ui': '长期课程阅读器', 'help_controller': '控件解释', 'control_help': '逐步讲解',
}

ROUTES = {
    '_build_main': '历史回测 → 展开运行控制；暂停、继续、单步与速度用于检查历史执行过程',
    '_research_page': '左侧写策略 → 中央源码区',
    '_backtest_page': '历史回测；结果内页通过净值与回撤、价格与买卖点、操作记录、运行依据和诊断页签进入',
    '_live_page': '模拟交易；策略交易、行情快照、账户规则与依据、手动练习通过页签切换',
    '_learning_page': '左侧量化课程；只显示 72 课',
    '_build_library': '账户与记录；选择记录只查看，打开详情进入对应模式的工作区',
    '_build_parameters': '写策略 → 右侧基本信息、参数设置或回测参数；检查参数位于参数设置内',
    'rebuild_parameters': '写策略 → 参数设置，先点击检查参数生成当前模型的字段',
    '_build_bottom': '视图 → 账户与执行 → 对应持仓、委托、成交、日志或权益流水页签',
    'open_data_center': '左侧数据中心，或 Ctrl+D',
    'download_dialog': '左侧数据中心 → 下载历史行情',
    '_build_menu': '主窗口顶部文件、视图或帮助菜单，先展开再选择具体命令',
}


def main():
    root = Path(__file__).resolve().parents[1] / 'src/astock/course_content'
    rows = json.loads((root / 'interface_controls.json').read_text(encoding='utf-8'))
    target = root / 'manual/controls'
    target.mkdir(parents=True, exist_ok=True)
    entries = []
    for row in rows:
        if not row.get('reviewed') or not row.get('explanation'):
            raise ValueError('未复核的控件不能发布手册：' + row['id'])
        area = AREAS[Path(row['source']).stem]
        route = ROUTES.get(row['context'].split('.')[-1], area) if Path(row['source']).stem == 'window' else area
        title = row.get('title') or row['label']
        relative = 'manual/controls/' + row['id'] + '.md'
        body = '# ' + title + '\n\n'
        body += '## 在哪里\n\n' + route + '。可在目标控件获得焦点后按 F1，或按 Shift+F1 再点选它查看说明。\n\n'
        body += '## 用途与操作\n\n' + row['explanation'] + '\n\n'
        body += '## 完成后核对\n\n' + row['steps'] + '\n\n'
        body += '## 不可用或未出现时\n\n' + row['unavailable'] + '\n\n'
        body += '隐藏的面板可从“视图”菜单显示；独立窗口的控件需要先进入该窗口。讲解不代点击业务按钮，关闭讲解不停止当前策略。\n'
        (root / relative).write_text(body, encoding='utf-8')
        entries.append({'id': 'help-' + row['id'], 'kind': 'manual', 'module': area,
                        'title': title, 'status': 'published', 'version': 1, 'body': relative,
                        'help_id': row['id']})
    path = root / 'catalogue.json'
    for task in json.loads((root / 'operation_paths.json').read_text(encoding='utf-8')):
        relative = 'manual/task-' + task['id'] + '.md'
        body = '# ' + task['title'] + '\n\n这份任务清单是离线核对资料。首次操作引导统一从「帮助 → 使用教程重放」进入，不自动执行业务动作。\n\n'
        for index, step in enumerate(task['steps'], 1):
            body += f"## {index}. {step['title']}\n\n位置：{step['route']}\n\n{step['instruction']}\n\n完成后核对：{step['expect']}\n\n"
        (root / relative).write_text(body, encoding='utf-8')
        entries.append({'id': 'task-' + task['id'], 'kind': 'manual', 'module': '完整操作任务',
                        'title': task['title'], 'status': 'published', 'version': 1, 'body': relative})
    current = json.loads(path.read_text(encoding='utf-8'))
    current = [e for e in current if not e['id'].startswith(('help-', 'control-', 'task-'))]
    path.write_text(json.dumps(current + entries, ensure_ascii=False, indent=2), encoding='utf-8')
    print('控件说明条目：', len(entries))


if __name__ == '__main__':
    main()
