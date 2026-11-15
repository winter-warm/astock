"""Stable product-control identities, separate from stylesheet object names."""
import json
from functools import lru_cache
from html import escape
from pathlib import Path


@lru_cache(maxsize=1)
def help_entries():
    path = Path(__file__).with_name('course_content') / 'interface_controls.json'
    if not path.exists():
        return {}
    return {row['id']: row for row in json.loads(path.read_text(encoding='utf-8'))}


def help_target(widget, identity):
    widget.setProperty('helpId', identity)
    entry = help_entries().get(identity, {})
    if entry.get('explanation'):
        widget.setWhatsThis('<p>' + escape(entry['explanation']) + '</p><p>'
                           + escape(entry.get('steps', '')) + '</p>')
    return widget


def describe(widget):
    identity = widget.property('helpId')
    return help_entries().get(identity, {})


def runtime_details(widget):
    """Explain the actual tabs/columns/ranges, including generated parameter fields."""
    from PySide6 import QtCore, QtWidgets
    parts = []
    if isinstance(widget, (QtWidgets.QTableView, QtWidgets.QTreeView)) and widget.model():
        model = widget.model()
        headers = [str(model.headerData(c, QtCore.Qt.Orientation.Horizontal) or '')
                   for c in range(model.columnCount(QtCore.QModelIndex()))]
        parts.append('当前表格列：' + '、'.join(headers) + f'。共 {model.rowCount(QtCore.QModelIndex())} 行。')
    if isinstance(widget, QtWidgets.QTabWidget):
        parts.append('可切换页签：' + '、'.join(widget.tabText(i) for i in range(widget.count())))
    if isinstance(widget, QtWidgets.QComboBox):
        parts.append('当前选择：' + widget.currentText())
    if isinstance(widget, (QtWidgets.QSpinBox, QtWidgets.QDoubleSpinBox)):
        parts.append(f'当前值 {widget.prefix()}{widget.value()}{widget.suffix()}；允许范围 {widget.minimum()} 至 {widget.maximum()}，步长 {widget.singleStep()}。')
    if isinstance(widget, QtWidgets.QAbstractButton):
        parts.append('当前按钮：' + widget.text())
    if widget.accessibleName():
        parts.append('字段名称：' + widget.accessibleName())
    return '\n'.join(parts)


def resolve_target(widget):
    """Map Qt implementation children back to the nearest owned control."""
    from PySide6 import QtWidgets
    if isinstance(widget, QtWidgets.QMenu) and widget.activeAction():
        entry = describe(widget.activeAction())
        if entry:
            return widget, entry
    while isinstance(widget, QtWidgets.QWidget):
        entry = describe(widget)
        if entry:
            return widget, entry
        if widget.objectName() == 'qt_toolbar_ext_button':
            return widget, {'title': '工具栏更多按钮', 'explanation': '窗口较窄时，工具栏放不下的命令收进这个箭头按钮。',
                            'steps': '点击展开被隐藏的工具栏命令；选择前核对名称与当前账户。增大窗口可让更多按钮直接显示。'}
        if isinstance(widget, QtWidgets.QToolButton) and widget.defaultAction():
            entry = describe(widget.defaultAction())
            if entry:
                return widget, entry
        if isinstance(widget, QtWidgets.QLabel) and widget.text():
            return widget, {'title': '当前提示 / 状态读数', 'explanation': widget.text(),
                            'steps': '这是一项只读提示或读数。结合旁边的字段名称、单位和状态理解，阅读它不会改变账户。'}
        if isinstance(widget, QtWidgets.QMenuBar):
            return widget, {'title': '主菜单', 'explanation': '文件：模型保存与退出；视图：面板、主题和布局；帮助：课程、逐项讲解、任务预览和接口。',
                            'steps': '点击菜单标题展开，移动到条目查看名称和快捷键；Esc 关闭菜单。条目获得焦点时按 F1 查看详情。'}
        if isinstance(widget, QtWidgets.QDockWidget):
            return widget, {'title': widget.windowTitle(), 'explanation': '可停靠面板。拖动标题栏移动或浮动，双击标题栏切换浮动，关闭后可从视图菜单重新显示。',
                            'steps': '调整面板仅改变布局；恢复默认布局会还原面板位置，不清空交易记录。'}
        if isinstance(widget, QtWidgets.QInputDialog):
            return widget, {'title': widget.windowTitle(), 'explanation': '按窗口提示输入名称或数值，再选择确定或取消。模型名称需非空且不与已有模型重名。',
                            'steps': '确定提交当前输入；取消或 Esc 返回，不建立新模型。新建与另存副本会在确认有效名称后保存原模型。'}
        if isinstance(widget, QtWidgets.QMessageBox):
            return widget, {'title': widget.windowTitle(), 'explanation': widget.text(),
                            'steps': '先阅读具体提示。确定关闭信息提示；询问是否替换草稿时，只有选择是才执行替换，否或关闭保留草稿。'}
        widget = widget.parentWidget()
    return None, None


def visible_targets(surface):
    from PySide6 import QtWidgets
    found, seen = [], set()
    for widget in [surface] + surface.findChildren(QtWidgets.QWidget):
        if not widget.isVisible():
            continue
        target, entry = resolve_target(widget)
        if target is not None and id(target) not in seen:
            seen.add(id(target))
            found.append((target, entry))
    return found
