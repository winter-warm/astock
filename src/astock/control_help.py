"""Explicit explanations for registered controls; tours never trigger business actions."""
from astock.help_registry import help_target
from PySide6 import QtCore, QtWidgets
from astock.help_registry import visible_targets, runtime_details

CONTROL_HELP = [['mode_combo', '运行模式', '选择历史回测、快照回放或实时仿真。历史数据与模式必须匹配；切换模式不会把日线转换成快照。', '先确认数据种类，再选择模式。回测和回放可单步，实时仿真依赖实际到达的报价。'], ['start_button', '开始运行', '使用当前策略、数据和参数创建独立运行。不是继续旧账户；已有结果会保留。', '先保存并检查模型参数，核对资金和费用，再点击。若账户正在准备，等待结果或取消准备。'], ['speed_combo', '快照回放速度', '只调整快照回放等待间隔；K 线回测自动尽快计算，此项禁用。', '1×按报价原始间隔等待，5×缩短为五分之一，单次最多等60秒。K 线逐步观察请用暂停和下一时刻。'], ['dataset_combo', '数据集', '选择本次历史研究使用的数据。教学数据为合成，真实数据可能因权益或规则缺失而不能回测。', '选中后检查预览、日期、来源、频率与覆盖状态。数据中心的“使用所选数据”会更新这里。'], ['symbol_input', '在线证券代码', '指定下一次连接行情订阅的证券，最多 20 个；代码带交易所后缀。', '例如 600000.SH,510300.SH。可通过证券目录按名称加入；修改后需重新连接，既有策略账户仍使用创建时的证券。'], ['capital', '初始虚拟资金', '指定新运行起始资金，单位元。它不是券商账户资金。', '保持其他条件相同再比较本金变化。修改不会重写已有运行的初始资金。'], ['commission', '佣金', '佣金费率，单位万分之。例如 3 表示万分之三，而不是百分之三。', '同时核对最低佣金。小额频繁交易可能主要受最低收费影响。'], ['minimum_fee', '最低佣金', '每笔收费约定中的最低佣金，单位元。具体累计方式以运行依据和流水为准。', '比较费用实验时只修改一个参数，运行后查看成交费用和汇总费用。'], ['participation', '成交参与率', '限制模拟订单可消耗本次可见流动性的比例，单位百分比；10表示10%，不是成交概率。', '从10改成1后比较部分成交与等待。报价可见数量不足时仍可能无法成交，同一时刻的可见流动性有限。'], ['slippage', '滑点', '按证券最小价格单位向不利方向调整模拟成交价格。数值 1 不是统一的 1 元。', '先核对证券价格单位，再比较 1 与 3 的结果。增加滑点不能绕过委托限价。'], ['position_limit', '仓位上限', '限制单只证券的持仓额度，单位为账户权益的百分比；例如50表示50%。检查时计入已有持仓、同标的待买委托和本次新买金额。', '先核对单标的目标仓位，再填写上限。改动用于新运行，不会把旧账户自动调仓。'], ['order_limit', '委托金额上限', '限制单笔委托金额，单位元。它限制成交价乘委托数量对应的金额，不是股数，也不是账户权益百分比。', '下单前对照价格与数量估算金额；被拒绝时查看具体原因，不要重复提交绕过限制。'], ['connect_button', '连接行情', '建立或断开行情连接；连接本身不表示策略已经启动。', '先设置证券，连接后观察来源时间、接收时间与数据年龄。休市返回报价不意味着可以交易。'], ['refresh_live_rule_button', '更新当日规则', '为所选在线账户取得当日 ETF 规则，成功后由用户继续策略。', '跨日暂停后选择原账户，点击更新，核对完成提示后再继续。更新失败不推测使用新规则。'], ['cancel_live_rule_button', '取消准备', '取消后台账户或规则准备，避免继续等待。', '取消后查看状态，确认没有新账户；不要把取消当作已有账户的停止并撤单。'], ['manual_symbol', '手动证券', '填写练习账户里要下单的证券代码。', '先建立手动练习账户，再核对代码是否属于账户证券；它与自动策略账户分离。'], ['manual_side', '委托方向', '选择买入或卖出。卖出需要可卖数量，不仅是持有数量。', '核对所选账户与持仓，特别留意当天新买份额可能尚不可卖。'], ['manual_qty', '委托数量', '输入股数或份额，不是交易金额。', '核对证券买入单位、可用资金及可卖数量；错误原因会显示在委托状态中。'], ['manual_price', '委托限价', '买入能接受的最高价或卖出能接受的最低价。', '可使用取对手价辅助填入，但提交前仍需核对。最新价不等于当前对手价，也不保证成交。'], ['create_manual_button', '建立练习账户', '创建独立虚拟手动账户，不会启动自动策略或连接券商。', '先准备行情和证券，再建立账户；需要核对规则时等待后台完成或取消准备。'], ['chart_symbol', '图表证券', '切换结果图表所查看的证券，不会改变已经运行的数据或账户。', '选择证券后再点击对应成交，核对图表时间和买卖理由。'], ['cancel_preview_button', '取消预览加载', '停止后台读取图表预览，不删除数据文件。', '大数据加载中可以取消；重新选择数据时只接受最后一次选择的结果。'], ['cancel_import_button', '取消数据导入', '停止当前数据包校验，不发布未完成导入。', '取消后可修改输入文件重试；完整通过校验的数据才加入数据中心。'], ['analysis_expand', '展开分析', '临时收起辅助面板，为结果图表腾出空间。', '再次点击或离开工作区还原。需要持仓和成交时可从视图菜单恢复底部面板。']]
# Stable identities are attribute-based, independent of displayed text and geometry.

class ControlTour(QtWidgets.QDialog):
    def __init__(self, window, surface=None):
        surface = surface or window
        super().__init__(surface)
        self.window = window
        self.setWindowTitle("当前界面逐项讲解")
        self.resize(500, 290)
        self.targets = [(widget, entry.get('title') or entry.get('label') or widget.accessibleName() or '当前控件',
                         entry['explanation'], entry.get('steps', '') + '\n' + runtime_details(widget))
                        for widget, entry in visible_targets(surface)]
        for identity, title, meaning, steps in CONTROL_HELP:
            target = getattr(window, identity, None)
            if target is not None:
                if target.isVisible() and all(target is not row[0] for row in self.targets):
                    self.targets.append((target, title, meaning, steps))
        self.index = 0
        layout = QtWidgets.QVBoxLayout(self)
        self.text = QtWidgets.QLabel()
        self.text.setWordWrap(True)
        self.text.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        layout.addWidget(self.text)
        row = QtWidgets.QHBoxLayout()
        for title, callback in [("上一步", lambda: self.advance(-1)),
                                ("下一步", lambda: self.advance(1)),
                                ("结束讲解", self.close)]:
            button = help_target(QtWidgets.QPushButton(title), 'control_help.ControlTour.__init__.button')
            button.clicked.connect(callback)
            row.addWidget(button)
        layout.addLayout(row)
        self.band = None
        self.finished.connect(self.cleanup)
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.track)
        self.timer.start(100)
        self.render()

    def advance(self, delta):
        if self.targets:
            self.index = max(0, min(len(self.targets)-1, self.index + delta))
            self.render()

    def render(self):
        if self.band:
            self.band.hide()
            self.band.deleteLater()
            self.band = None
        if not self.targets:
            self.text.setText("当前页面没有已登记且可见的讲解目标。请查阅操作手册；此处不代表全界面覆盖已经完成。")
            return
        target, title, meaning, steps = self.targets[self.index]
        self.text.setText(f"{self.index+1} / {len(self.targets)} · {title}\n\n{meaning}\n\n操作：{steps}\n\n讲解不会点击或修改控件；Esc 退出。")
        try:
            parent = target.parentWidget()
            while parent:
                if isinstance(parent, QtWidgets.QScrollArea):
                    parent.ensureWidgetVisible(target)
                parent = parent.parentWidget()
            self.band = QtWidgets.QRubberBand(QtWidgets.QRubberBand.Shape.Rectangle, target.window())
            self.band.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            self.track()
        except RuntimeError:
            self.text.setText("目标窗口已关闭，请结束讲解后重新打开。")

    def track(self):
        if not self.band or not self.targets:
            return
        target = self.targets[self.index][0]
        try:
            if not target.isVisible():
                self.band.hide()
                return
            self.band.setGeometry(QtCore.QRect(target.mapTo(target.window(), QtCore.QPoint()), target.size()))
            self.band.show()
            self.band.raise_()
        except RuntimeError:
            self.cleanup()
            self.text.setText("目标已销毁，讲解暂停。请结束后重新打开。")

    def cleanup(self, *_):
        self.timer.stop()
        if self.band:
            try:
                self.band.hide()
                self.band.deleteLater()
            except RuntimeError:
                pass
            self.band = None

    def closeEvent(self, event):
        self.cleanup()
        event.accept()

