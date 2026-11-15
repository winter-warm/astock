"""A single first-launch product tour; page navigation never performs trading actions."""
from PySide6 import QtCore, QtWidgets
from shiboken6 import isValid

from astock.help_registry import help_target


STATE_KEY = 'onboarding_v1'
# Chapter, page, target, title, purpose, how to use, expected result.
STEPS = (
    ('写策略', 0, 'nav:0', '先分清三个工作区',
     '写策略负责源码和参数；历史回测负责历史数据实验；模拟交易负责正在运行的虚拟账户。账户与记录统一归档、查看和比较。',
     '从左侧“写策略”开始。教程只切页和高亮，所有保存、运行、连接和下单都由你自行点击。',
     '中央是代码区，右侧是参数区域。无需寻找另一个编辑窗口。'),
    ('写策略', 0, 'new_strategy_button', '新建一个自己的策略',
     '新建策略会建立独立名称和初始源码。名称用于之后选择策略和辨认运行记录。',
     '点击后填写一个未使用的名称；若只想阅读示例，下一步使用模板选择。不要把不同实验都保存成同一个名字。',
     '确认代码区上方显示你填写的策略名。取消名称窗口不会新建。'),
    ('写策略', 0, 'template_button', '选择模板或已保存策略',
     '这里集中列出内置模板和自己的已保存策略。选择策略会把相应源码和参数放入编辑区。',
     '先保存需要保留的修改，再打开列表，选择一个模板或已有策略并编辑。内置双均线适合熟悉完整流程。',
     '核对编辑区上方的名称和源码内容，不要只凭列表中的选中行判断已经载入。'),
    ('写策略', 0, 'editor', '在代码区编写规则',
     'PARAMETERS 声明可调参数；initialize 初始化策略，on_bar 处理 K 线，on_quote 处理快照。此处编辑不会自动运行。',
     '先改一个条件或参数，检查 Python 缩进。策略接口按钮可查看实际支持的方法；不要直接套用其他平台 API。',
     '代码区中的内容是当前草稿。去回测会带上这份草稿，不会替换已经完成的运行快照。'),
    ('写策略', 0, 'check_parameters_button', '在右侧检查参数',
     '检查参数位于右侧“参数设置”，读取代码中的 PARAMETERS 并更新下方参数表单。它不执行买卖逻辑，也不代表回测通过。',
     '修改 PARAMETERS 后点击检查参数；若报语法或类型错误，按提示修正代码，再检查一次。',
     '下方出现当前声明对应的名称、类型和范围；不是只看按钮有没有反应。'),
    ('写策略', 0, 'param_widget', '设置本次实验的参数值',
     '这里的值与源码声明的默认值有区别：声明决定表单，表单里的当前值决定本次实验使用什么参数。',
     '例如先只改快均线周期，保持慢周期及其他条件不变。输入合法范围后再保存或去回测。',
     '记住改了哪一个值；运行后可在“运行依据”核对实际冻结的参数。'),
    ('写策略', 0, 'save_strategy_button', '保存源码和参数',
     '保存或 Ctrl+S 把当前名称、源码和参数写入本地策略库。它不会开始回测，也不会更新旧运行的源码快照。',
     '需要保留两个实验版本时先另存副本，再保存修改。已有草稿也可以直接去回测，但要看清待运行策略说明。',
     '看状态栏的保存提示，并核对当前策略名。保存策略与导出运行报告是两件事。'),
    ('数据与费用', 5, 'data_overview_table', '选择本次回测的数据',
     '历史数据表列出名称、类型、来源、起止日期和记录数。K 线用于历史回测，报价快照用于回放，两者不能混用。',
     '单击要使用的数据行。第一次可以用明确标注的教学日线；真实数据先检查缺口、复权和证券规则。',
     '下方提示已选择的数据名称。选择数据不会启动运行。'),
    ('数据与费用', 0, 'dataset_combo', '核对策略页的数据输入',
     '右侧基本信息中的数据集选择与数据中心保持一致。它决定可用证券、周期和日期覆盖。',
     '展开列表核对名称和类型；想换证券或周期时先准备对应的数据集，不能只改图上的证券下拉框。',
     '确认这里和数据中心选中的是同一份数据。基准与测试区间随后在回测设置中核对。'),
    ('数据与费用', 0, 'commission', '把交易费用算进去',
     '佣金输入单位是万分之：填 3 表示万分之三。最低佣金按元计。忽略最低佣金会明显高估小额频繁交易的结果。',
     '在右侧“回测参数”核对佣金率与最低佣金；按实际模拟假设填写，万分之三在这里填 3，不填 0.0003。',
     '本次回测的费用参数会进入运行依据。与其他运行比较时，费用假设应一致。'),
    ('数据与费用', 0, 'slippage', '理解滑点和成交限制',
     '滑点使用证券最小报价单位的档数；成交参与率限制可参与的行情成交量。限价、资金和规则也会影响是否成交。',
     '核对滑点档数、参与率、单证券仓位比例和单笔金额上限。先读字段单位，再填数字。',
     '出现未成交或拒单时查看委托说明；不能把发出委托当成已经买到。'),
    ('回测准备', 0, 'strategy_dialog.backtest_button', '把当前策略带到回测',
     '去回测会选择当前编辑区的策略源码和参数，进入历史回测页面。它只是准备实验，不会立即开始。',
     '编写完成后点击去回测，再核对下一步的待运行策略摘要。若当前有未保存修改，应按草稿看待。',
     '待运行策略应与刚才编辑的名称一致。旧结果仍属于旧运行，不会变成新策略的结果。'),
    ('回测准备', 1, 'backtest_strategy_label', '先看“待运行策略”',
     '这里说明接下来要运行哪份策略。它与下方已经显示的结果来源分开，避免把上一份结果误认为当前草稿的结果。',
     '核对名称、来源以及草稿提示。若刚从写策略进入，应看到刚编辑的策略；换策略时用旁边的选择策略。',
     '准备区的策略正确后再配置数据和区间；不要从净值曲线的标题推测下一次会运行谁。'),
    ('回测准备', 1, 'backtest_choose_button', '在回测页更换策略',
     '选择策略让你明确选择当前编辑草稿、模板或已保存版本，避免回测入口依赖一个看不见的编辑器状态。',
     '打开选择窗口，读清策略来源，确认所需版本。想修改源码时返回写策略，不要在结果页猜测修改是否生效。',
     '选择完成后待运行策略摘要更新；已有历史结果的来源说明保持原样。'),
    ('回测准备', 1, 'backtest_settings_button', '设置区间、基准和本金',
     '回测设置可选择数据集和初始资金。K 线支持日期区间与收益基准，快照使用完整录制区间；费用沿用右侧撮合设置。',
     '点击后在顶部选择并核对数据。要按日期回测就选择 K 线，再填日期、基准和本金，最后保存。取消不应用修改。',
     '保存后核对主页面的运行类型和数据；日期须在覆盖范围内。保存不会启动运行，也不会改写旧结果。'),
    ('回测准备', 1, 'backtest_settings_button', '使用前半段和后半段',
     '全部区间、前半段探索和后半段检验按日历日期分割，不保证两段行情条数相等；每次都从空仓开始。',
     '先在前半段研究，固定策略后另开一次后半段运行。反复看后半段再调参数，会使它失去独立检验意义。',
     '保存后核对实际开始、结束日期。快捷选择不是自动完成样本外验证。'),
    ('回测运行', 1, 'backtest_start_button', '明确点击才开始回测',
     '开始回测创建一次独立历史实验，冻结策略源码、参数、数据和费用；不会向券商发真实订单。',
     '先逐项核对待运行策略和设置，再点击开始。准备中或已有不允许重复的操作时，应等待状态提示。',
     '看到运行状态和进度变化。没有交易也可能是条件未满足，需看日志与委托，不能只看曲线。'),
    ('回测运行', 1, 'backtest_controls_toggle', '需要时再展开调试控制',
     '通常只需设置和开始回测。快照回放速度、暂停、继续、下一时刻和停止放在折叠的调试控制中；K 线回测不使用播放倍率。',
     '想逐步观察策略时展开；只看完整结果时保持折叠。调试控制作用于本页的历史运行。',
     '展开只改变显示，不创建新账户，也不会暂停当前运行。'),
    ('回测运行', 1, 'run_toolbar', '暂停、继续与下一时刻',
     '暂停让历史时间停住，继续恢复自动推进；下一时刻推进一个行情时刻，该时刻可能包含多只证券，不等于一笔成交。',
     '先暂停，再单步观察委托何时提交、后续行情何时成交。没有当前运行或状态不适合时，按钮会禁用。',
     '查看运行时点、委托和成交时间的变化。快照回放速度仅在快照模式可调，5×把等待缩短为五分之一；K 线回测时禁用。'),
    ('回测运行', 1, 'run_toolbar', '何时停止当前实验',
     '停止并撤单结束当前实验并处理尚未成交的委托；这不是重新开始。再次开始会建立新的独立运行。',
     '需要中断实验时使用停止，再到记录中核对状态和冻结资金。不要重复点击开始来代替继续。',
     '当前运行显示已停止或已完成。停止的结果可能没有覆盖完整区间，比较前要确认完成状态。'),
    ('读取结果', 1, 'result_description', '先核对“结果来自谁”',
     '结果来源属于已经创建的运行，包含策略名称、状态和数据；它可能与上方准备中的下一份策略不同。',
     '每次换策略或从记录打开结果时，先读这行，再看收益。不要把尚未运行的草稿与上一条曲线混为一谈。',
     '确认结果对应的策略、数据和运行状态都符合你要分析的实验。'),
    ('读取结果', 1, 'backtest_overview.performance', '从绩效表开始读结果',
     '累计收益、最大回撤、费用和成交数共同说明表现。盈利卖出占比不是完整买卖回合胜率，基准是所选证券的价格收益。',
     '先看费用和成交是否合理，再看收益与回撤；同时读数据来源与范围说明。合成数据只能验证流程。',
     '指标与当前结果来源一致。没有成交时，不要把零费用或平直净值误认为策略已经验证。'),
    ('读取结果', 1, 'backtest_overview.price_chart', '查看价格与买卖点',
     '价格图显示所选证券及成交标记；下方权益和回撤属于整个账户。切换主图证券不会改变整户收益。',
     '用主图证券下拉框选择对象，滚轮缩放、拖动查看局部；点成交明细追溯当时价格与策略理由。',
     '核对买卖点时间和对应成交。图中可用观察窗口不一定覆盖整个数据文件。'),
    ('读取结果', 1, 'manifest_text', '用运行依据复核实验条件',
     '运行依据保存这次实验的策略源码、参数、数据版本和规则等信息，是复现结果的依据。它不会跟随当前草稿变化。',
     '在结果页切到运行依据，逐项比较源码、参数、日期、基准和费用；改过配置时尤其要检查。',
     '能说明本次结果用了什么输入，而不只记住一个收益数字。'),
    ('读取结果', 1, 'activity_orders', '委托与成交为什么不同',
     '委托表记录请求、限价、数量、成交量和状态。已提交不等于已成交，部分成交也不等于全部成交。',
     '切到操作记录的下单与状态，读最后的理由或状态说明。再到成交明细核对实际成交时间、数量、价格和费用。',
     '拒单或未成交能找到原因，例如资金、限价、交易单位、数据或规则约束。'),
    ('读取结果', 1, 'activity_trades', '从一笔成交追到策略理由',
     '成交明细是实际模拟买卖的记录，包含对应订单、费用和理由；一张委托可以产生多笔成交。',
     '单击一笔成交，再看价格与买卖点中的定位和说明。需要排错时查看同组的策略日志。',
     '能把订单、成交、图上时点和策略条件对应起来，而不是只看到总成交数。'),
    ('读取结果', 1, 'diagnostics', '看分月表现与回撤诊断',
     '分月表现帮助识别收益是否集中于少数阶段；回撤诊断说明损失怎样形成。短样本统计不代表稳定规律。',
     '把表现好的月份和差的月份分别与交易明细核对，再决定下一项实验；不要只挑一段漂亮曲线。',
     '报告、比较和历史查询统一到“账户与记录”，这里专注解释当前历史实验。'),
    ('模拟交易', 2, 'connect_button', '连接行情，不等于开始交易',
     '模拟交易专门管理实时仿真和手动虚拟账户。连接行情只取得报价，不会自动创建策略账户或下单。',
     '先确认证券列表，再连接行情；在行情快照中检查时间和年龄。休市或网络问题可能使报价停止更新。',
     '看到连接状态及有时间戳的报价后，再判断是否适合启动仿真。'),
    ('模拟交易', 2, 'trading_tasks.create_button', '创建一个仿真账户',
     '新建策略交易需要选择策略、证券和初始虚拟资金，确认创建才会准备规则并启动独立账户。',
     '在表单中核对每项，再点击创建并启动仿真；不准备启动时取消。不要把选择历史账户当成新建。',
     '账户列表新增独立标识和状态。这里不显示历史回测账户，真实资金不参与。'),
    ('模拟交易', 2, 'trading_tasks.accounts', '选中正在管理的账户',
     '每行是一个独立的实时仿真或手动账户。名称相同也可能是不同账户，要结合账户标识和状态判断。',
     '选择一行后查看账户，再操作暂停、继续或停止。离开模拟页不会自动停止后台账户。',
     '控制栏和详情指向刚选中的账户，而不是历史回测页的运行。'),
    ('模拟交易', 2, 'trading_stop_button', '结束仿真并核对委托',
     '停止并撤单用于结束当前虚拟账户的运行。暂停、继续与停止各有用途，不能用重复启动代替恢复。',
     '结束观察时点击停止，再核对未成交委托是否撤销及冻结资金是否释放；已结束账户只能查看历史结果。',
     '状态不再运行，未完成任务应有明确说明。页面切换本身不会提交委托。'),
    ('记录与课程', 4, 'home_accounts.selector', '在归档中选择历史运行',
     '账户与记录统一保存历史回测、快照回放和仿真账户的记录。这里用于查询、对比和导出，不承担交易控制。',
     '按模式、策略名和运行标识选择记录。历史回测详情回到历史回测页，仿真详情回到模拟交易页。',
     '只读摘要显示已保存快照的时点，选择记录不会启动或恢复账户。'),
    ('记录与课程', 4, 'home_accounts.report_button', '导出所选记录的报告',
     '导出使用当前归档选择的运行，包含结果与实验条件；它不是导出当前编辑器的 Python 源码。',
     '先确认归档中选的是哪条记录，再导出。等待完成提示后打开报告；没有选择或数据不足时按钮不可用。',
     '报告里的运行标识与选中记录相同，保留失败或未完成状态的说明。'),
    ('记录与课程', 4, 'home_accounts.compare_button', '比较已有运行',
     '比较用于检查多次实验的差异。收益高低只有在数据、区间、资金、费用和完成状态可比时才有意义。',
     '打开运行对比，先核对比较依据，再看收益与回撤。一次只改一个因素，才能解释差异来自哪里。',
     '能指出两次运行究竟改了哪一项。比较不会重新运行策略。'),
    ('记录与课程', 3, 'nav:3', '继续学习 72 课',
     '量化课程提供指标、代码、实验与练习。课程阅读和自测进度独立于交易账户，初始化应用也保留这些学习记录。',
     '按模块阅读、运行示例和核对答案。忘记操作时从帮助重放本教程，可通过上方章节直接跳到回测或仿真。',
     '完成后返回写策略动手。教程完成不代表策略盈利，也不会替你完成量化课程。'),
)



class OnboardingTour(QtWidgets.QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.index = 0
        self.band = None
        self.target = None
        self.setWindowTitle('使用教程')
        self.setModal(False)
        self.setWindowFlag(QtCore.Qt.WindowType.Tool, True)
        available = window.screen().availableGeometry()
        self.resize(min(470, available.width() - 24), min(430, available.height() - 70))
        layout = QtWidgets.QVBoxLayout(self)
        self.chapter = help_target(QtWidgets.QComboBox(), 'onboarding.OnboardingTour.__init__.chapter')
        self.chapter.setAccessibleName('使用教程章节')
        for index, step in enumerate(STEPS):
            if not index or step[0] != STEPS[index - 1][0]:
                self.chapter.addItem(step[0], index)
        self.chapter.activated.connect(self.choose_chapter)
        layout.addWidget(self.chapter)
        self.original_debug = None
        self.heading = QtWidgets.QLabel()
        self.heading.setWordWrap(True)
        self.heading.setStyleSheet('font-size: 16px; font-weight: 600;')
        layout.addWidget(self.heading)
        self.reading = QtWidgets.QScrollArea()
        self.reading.setWidgetResizable(True)
        self.reading.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        content = QtWidgets.QWidget()
        content_layout = QtWidgets.QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 6, 0)
        self.reading.setWidget(content)
        layout.addWidget(self.reading, 1)
        self.explanation = QtWidgets.QLabel()
        self.explanation.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        self.explanation.setWordWrap(True)
        content_layout.addWidget(self.explanation)
        self.action = QtWidgets.QLabel()
        self.action.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        self.action.setWordWrap(True)
        content_layout.addWidget(self.action)
        self.expected = QtWidgets.QLabel()
        self.expected.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        self.expected.setWordWrap(True)
        content_layout.addWidget(self.expected)
        content_layout.addStretch()
        row = QtWidgets.QHBoxLayout()
        self.previous = help_target(QtWidgets.QPushButton('上一步'), 'onboarding.OnboardingTour.__init__.previous')
        self.next = help_target(QtWidgets.QPushButton('下一步'), 'onboarding.OnboardingTour.__init__.next')
        self.skip = help_target(QtWidgets.QPushButton('暂时跳过'), 'onboarding.OnboardingTour.__init__.skip')
        self.previous.clicked.connect(lambda: self.advance(-1))
        self.next.clicked.connect(lambda: self.advance(1))
        self.skip.clicked.connect(self.close)
        row.addWidget(self.previous)
        row.addWidget(self.next)
        row.addWidget(self.skip)
        layout.addLayout(row)
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.track)
        self.timer.start(100)
        self.finished.connect(self.finish_state)
        self.render()

    def advance(self, direction):
        if direction > 0 and self.index == len(STEPS) - 1:
            self.window.store.set_setting(STATE_KEY, {'status': 'completed'})
            self.window.switch_workspace(0)
            self.close()
            return
        self.index = max(0, min(len(STEPS) - 1, self.index + direction))
        self.render()

    def choose_chapter(self, index):
        self.index = self.chapter.itemData(index)
        self.render()

    def resolve(self, identity):
        if identity.startswith('nav:'):
            return self.window.nav_group.button(int(identity[4:]))
        target = self.window
        for part in identity.split('.'):
            target = getattr(target, part, None)
            if target is None:
                break
        return target

    def reveal(self, identity):
        w = self.window
        settings = getattr(w, 'editor_settings', None)
        if settings:
            if identity in ('check_parameters_button', 'param_widget'):
                settings.setCurrentIndex(1)
            elif identity in ('commission', 'slippage'):
                settings.setCurrentIndex(2)
            elif identity == 'dataset_combo':
                settings.setCurrentIndex(0)
        if identity == 'data_overview_table' and hasattr(w, 'data_market_tabs'):
            w.data_market_tabs.setCurrentIndex(0)
        tabs = getattr(w, 'result_tabs', None)
        if tabs:
            if identity.startswith('backtest_overview.'):
                tabs.setCurrentWidget(w.backtest_overview)
            elif identity in ('manifest_text', 'diagnostics'):
                tabs.setCurrentWidget(getattr(w, identity))
            elif identity.startswith('activity_'):
                tabs.setCurrentWidget(w.activity_tabs.parentWidget())
                w.activity_tabs.setCurrentWidget(getattr(w, identity))
        live = getattr(w, 'live_tabs', None)
        if live and identity.startswith('trading_tasks.'):
            live.setCurrentWidget(w.trading_tasks)
        toggle = getattr(w, 'backtest_controls_toggle', None)
        if toggle is not None:
            if self.original_debug is None:
                self.original_debug = toggle.isChecked()
            toggle.setChecked(identity == 'run_toolbar' or self.original_debug)

    def render(self):
        chapter, page, identity, title, explanation, action, expected = STEPS[self.index]
        self.window.switch_workspace(page)
        self.reveal(identity)
        self.target = self.resolve(identity)
        blocker = QtCore.QSignalBlocker(self.chapter)
        self.chapter.setCurrentText(chapter)
        del blocker
        self.heading.setText(f'{self.index + 1} / {len(STEPS)}  {title}')
        self.explanation.setText('用途：' + explanation)
        self.action.setText('操作：' + action)
        self.expected.setText('核对：' + expected)
        self.reading.verticalScrollBar().setValue(0)
        self.previous.setEnabled(self.index > 0)
        self.next.setText('完成，开始写策略' if self.index == len(STEPS) - 1 else '下一步')
        if self.band:
            self.band.hide()
            self.band.deleteLater()
        self.band = QtWidgets.QRubberBand(QtWidgets.QRubberBand.Shape.Rectangle, self.window)
        self.band.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        # Scroll only presentation containers; do not synthesize business clicks.
        if self.target is not None:
            parent = self.target.parentWidget()
            while parent:
                if isinstance(parent, QtWidgets.QScrollArea):
                    parent.ensureWidgetVisible(self.target)
                parent = parent.parentWidget()
        self.track()
        self.place_card()

    def track(self):
        if self.band and self.target and isValid(self.target) and self.target.isVisible():
            self.band.setGeometry(QtCore.QRect(self.target.mapTo(self.window, QtCore.QPoint()), self.target.size()))
            self.band.show()
            self.band.raise_()
        elif self.band:
            self.band.hide()

    def place_card(self):
        # Place in an opposite corner so the highlighted editor/button stays visible.
        available = self.window.screen().availableGeometry()
        frame = self.window.frameGeometry()
        x = min(frame.right() - self.width() - 18, available.right() - self.width() - 8)
        y = min(frame.bottom() - self.height() - 48, available.bottom() - self.height() - 8)
        if self.target and isValid(self.target):
            center = self.target.mapToGlobal(self.target.rect().center())
            if center.x() > frame.center().x():
                x = frame.left() + 105
        self.move(max(available.left() + 8, x), max(available.top() + 8, y))

    def cleanup(self, *_):
        self.timer.stop()
        toggle = getattr(self.window, 'backtest_controls_toggle', None)
        if toggle is not None and self.original_debug is not None:
            toggle.setChecked(self.original_debug)
        if self.band:
            self.band.hide()
            self.band.deleteLater()
            self.band = None

    def closeEvent(self, event):
        self.finish_state()
        event.accept()

    def finish_state(self, *_):
        self.cleanup()
        if not self.window.closing:
            saved = self.window.store.setting(STATE_KEY, {})
            if saved.get('status') != 'completed':
                self.window.store.set_setting(STATE_KEY, {'status': 'skipped', 'step': self.index})


def open_onboarding(window, *, first_run=False, start_chapter=None):
    if window.closing:
        return None
    if first_run and window.store.setting(STATE_KEY, {}).get('status') in ('completed', 'skipped'):
        return None
    previous = getattr(window, 'onboarding_dialog', None)
    if previous is not None and isValid(previous):
        previous.close()
        previous.deleteLater()
    window.onboarding_dialog = OnboardingTour(window)
    if start_chapter is not None:
        chapter_index = window.onboarding_dialog.chapter.findText(start_chapter)
        if chapter_index >= 0:
            window.onboarding_dialog.choose_chapter(chapter_index)
    window.onboarding_dialog.show()
    window.onboarding_dialog.raise_()
    return window.onboarding_dialog
