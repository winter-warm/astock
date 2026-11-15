"""Inline strategy workspace, sharing the actual editor and settings widgets."""
from astock.help_registry import help_target
from PySide6 import QtWidgets

from astock.ui_components import button, label


class StrategyEditorWindow(QtWidgets.QWidget):
    """Historical class name retained for integrations; now a main-window page."""

    def __init__(self, window, research_page):
        super().__init__(window)
        self.window = window
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        heading = QtWidgets.QHBoxLayout()
        heading.addWidget(label("写策略", "title"))
        heading.addWidget(label("编写 Python → 选择数据和参数 → 历史回测 → 模拟交易", "muted", True), 1)
        layout.addLayout(heading)
        actions = QtWidgets.QToolBar()
        actions.setMovable(False)
        self.new_button = help_target(button("新建策略", window.model_browser.new_model), 'strategy_editor_window.StrategyEditorWindow.__init__.new_button')
        actions.addWidget(self.new_button)
        self.library_button = help_target(button("模板与已存策略", window.open_strategy_library), 'strategy_editor_window.StrategyEditorWindow.__init__.library_button')
        actions.addWidget(self.library_button)
        self.save_button = help_target(button("保存", window.save_strategy), 'strategy_editor_window.StrategyEditorWindow.__init__.button')
        actions.addWidget(self.save_button)
        actions.addSeparator()
        self.backtest_button = help_target(button("去回测", window.go_backtest, True), 'strategy_editor_window.StrategyEditorWindow.__init__.button3')
        actions.addWidget(self.backtest_button)
        actions.addWidget(help_target(button("去模拟交易", lambda: window.switch_workspace(2)), 'strategy_editor_window.StrategyEditorWindow.__init__.button4'))
        actions.addWidget(help_target(button("数据预览", lambda: window.research_preview.setVisible(not window.research_preview.isVisible())), 'strategy_editor_window.StrategyEditorWindow.__init__.button5'))
        self.api_button = help_target(button("策略接口", window.show_api), 'strategy_editor_window.StrategyEditorWindow.__init__.button6')
        actions.addWidget(self.api_button)
        layout.addWidget(actions)
        self.guide_text = label("", "muted", True)
        self.guide_button = help_target(button("继续练习", lambda: window.learning.act()), 'strategy_editor_window.StrategyEditorWindow.__init__.guide_button')
        guide = QtWidgets.QHBoxLayout()
        guide.addWidget(self.guide_text, 1)
        guide.addWidget(self.guide_button)
        layout.addLayout(guide)
        self.guide_text.hide()
        self.guide_button.hide()
        self.split = QtWidgets.QSplitter()
        self.split.setChildrenCollapsible(False)
        self.split.addWidget(research_page)
        research_page.show()
        self.settings_slot = QtWidgets.QWidget()
        self.settings_slot.setMinimumWidth(280)
        self.settings_layout = QtWidgets.QVBoxLayout(self.settings_slot)
        self.settings_layout.setContentsMargins(0, 0, 0, 0)
        self.split.addWidget(self.settings_slot)
        self.split.setSizes([740, 330])
        self.split.setStretchFactor(0, 1)
        self.split.setStretchFactor(1, 0)
        layout.addWidget(self.split, 1)
        self.output = help_target(QtWidgets.QPlainTextEdit(), 'strategy_editor_window.StrategyEditorWindow.__init__.output')
        self.output.setReadOnly(True)
        self.output.setMaximumHeight(70)
        self.output.setPlaceholderText("策略运行后的日志显示在这里；编写或切换页面不会启动交易。")
        layout.addWidget(self.output)
        self.borrowed = None

    def open_editor(self):
        w = self.window
        if self.borrowed is None:
            self.borrowed = w.parameter_dock.widget()
            self.borrowed.setParent(self.settings_slot)
            self.settings_layout.addWidget(self.borrowed)
            self.borrowed.show()
        self.settings_slot.show()
        w.parameter_dock.hide()
        active = hasattr(w, 'learning') and w.learning.lesson is not None
        self.guide_text.setVisible(active)
        self.guide_button.setVisible(active)
        if hasattr(w, 'learning'):
            w.learning.render()
        self.output.setPlainText(w.log_view.toPlainText())

    def release_settings(self):
        if self.borrowed is not None:
            self.settings_layout.removeWidget(self.borrowed)
            self.window.parameter_dock.setWidget(self.borrowed)
            self.borrowed = None

    def show_help(self):
        self.window.show_api()

    def closeEvent(self, event):
        self.release_settings()
        event.accept()
