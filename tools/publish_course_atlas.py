"""Publish actual, reviewed native screenshots as an offline operation atlas."""
import argparse
import json
from pathlib import Path
import shutil


TITLES = {
    'workspace-0': '写策略：直接编写源码、调整参数与保存',
    'workspace-1': '历史回测：待运行策略与当前结果分开',
    'backtest-strategy-selection': '选择回测策略：草稿、模板和已保存版本',
    'backtest-run-controls': '回测运行控制：需要调试时才展开',
    'workspace-2': '模拟交易：账户、行情和手动练习',
    'workspace-4': '账户与记录：只读归档、导出与比较',
    'archive-tab-3': '归档配置：核对保存时的策略与参数',
    'workspace-5': '数据中心：证券目录与行情数据',
    'strategy-editor': '策略工作区：源码、参数和日志',
    'strategy-library': '模板与已存策略：选择要编辑的版本',
    'data-center': '数据中心：选择版本、检查与使用',
    'download': '历史下载：代码、频率、来源与日期',
    'catalog': '证券目录：搜索、多选与当前资料',
    'backtest-settings': '回测设置：区间、基准与本金',
    'rules': '历史规则：有效日期和资料来源',
    'preview-quality': '数据覆盖检查的讲解预览',
    'preview-report': '导出报告的讲解预览',
    'preview-compare': '运行对比的讲解预览',
    'preview-recover': '录制恢复的讲解预览',
    'new-trading-task': '新建策略交易表单',
    'course-q19': '长期课程：阅读、代码和自测',
    'first-run-tutorial': '首次使用引导：从写策略到回测与模拟交易',
    'tutorial-chapter-2': '回测准备教程：用途、操作与核对结果',
    'tutorial-chapter-3': '回测运行教程：先检查策略再开始',
    'tutorial-chapter-4': '结果阅读教程：辨认当前结果的来源',
    'initialize-confirmation': '初始化确认：不备份，保留学习进度',
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    args = parser.parse_args()
    report = json.loads((args.source / 'interface-report.json').read_text(encoding='utf-8'))
    if not report['passed']:
        raise ValueError('界面检查未通过，不能作为教程图解来源')
    root = Path(__file__).resolve().parents[1] / 'src/astock/course_content'
    images = root / 'images/interface'
    images.mkdir(parents=True, exist_ok=True)
    text = '# 界面图解：对照实际窗口找到操作位置\n\n'
    text += '这是随源码保存的界面核对资料，不占用 72 课课程目录。图中数据来自独立验收目录；空白任务预览不代表真实任务结果。黄色编号对应图下控件说明。应用操作请从“帮助 → 使用教程重放”开始。\n\n'
    for surface in report['surfaces']:
        name = surface['name']
        if name not in TITLES:
            continue
        source = args.source / (name + '-annotated.png')
        shutil.copy2(source, images / source.name)
        text += '## ' + TITLES[name] + '\n\n'
        text += f'![{TITLES[name]}](images/interface/{source.name})\n\n'
        for index, control in enumerate(surface['controls'], 1):
            text += f"{index}. {control['title']}\n"
        text += '\n窗口较小时可滚动右侧阅读区查看完整图解。编号对应当前截图，不用作控件身份；版本维护使用稳定 helpId。\n\n'
    (root / 'manual/interface-atlas.md').write_text(text, encoding='utf-8')
    path = root / 'catalogue.json'
    entries = json.loads(path.read_text(encoding='utf-8'))
    entries = [entry for entry in entries if entry['id'] != 'interface-atlas']
    entries.insert(1, {'id': 'interface-atlas', 'kind': 'manual', 'module': '界面图解',
                       'title': '界面图解：窗口、编号与操作位置', 'status': 'published', 'version': 1,
                       'body': 'manual/interface-atlas.md'})
    path.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding='utf-8')
    print('界面图解截图：', len(TITLES))


if __name__ == '__main__':
    main()
