"""Searchable native course reader; legacy practice evidence stays separate."""
from astock.help_registry import help_target
from PySide6 import QtCore, QtGui, QtWidgets
from astock.course_library import ROOT, catalogue, article, digest, resource
from astock.course_lab import CourseLab
from astock.course_reading import sections, check_answer


class CourseLibrary(QtWidgets.QWidget):
    def __init__(self, window, *, include_manuals=False):
        super().__init__()
        self.window = window
        self.entries = [e for e in catalogue() if include_manuals or e['kind'] == 'course']
        self.published = [e for e in self.entries if e.get('status') == 'published']
        self.state = window.store.setting('learning_library_v1', {})
        if not isinstance(self.state, dict):
            self.state = {}
        self.current = None
        self.example = None
        self.exported_path = None
        self.active = None
        self.texts = {e['id']: article(e) for e in self.published}
        layout = QtWidgets.QVBoxLayout(self)
        self.search = help_target(QtWidgets.QLineEdit(), 'course_ui.CourseLibrary.__init__.search')
        self.search.setPlaceholderText('搜索 72 课：课名、指标、术语或正文')
        layout.addWidget(self.search)
        self.bookmarks_only = help_target(QtWidgets.QCheckBox('只看书签'), 'course_ui.CourseLibrary.__init__.bookmarks_only')
        layout.addWidget(self.bookmarks_only)
        split = QtWidgets.QSplitter()
        self.tree = help_target(QtWidgets.QTreeWidget(), 'course_ui.CourseLibrary.__init__.tree')
        self.tree.setHeaderLabel('量化课程 · 12 模块 / 72 课')
        split.addWidget(self.tree)
        right = QtWidgets.QWidget()
        content = QtWidgets.QVBoxLayout(right)
        self.status = QtWidgets.QLabel()
        self.status.setWordWrap(True)
        content.addWidget(self.status)
        navigation = QtWidgets.QHBoxLayout()
        self.toc = help_target(QtWidgets.QComboBox(), 'course_ui.CourseLibrary.__init__.toc')
        self.toc.setAccessibleName('本课目录')
        self.toc.setMinimumContentsLength(12)
        self.toc.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.bookmark = help_target(QtWidgets.QPushButton('添加书签'), 'course_ui.CourseLibrary.__init__.bookmark')
        self.answers = help_target(QtWidgets.QCheckBox('显示练习答案'), 'course_ui.CourseLibrary.__init__.answers')
        navigation.addWidget(self.toc, 1)
        navigation.addWidget(self.bookmark)
        navigation.addWidget(self.answers)
        content.addLayout(navigation)
        self.body = help_target(QtWidgets.QTextBrowser(), 'course_ui.CourseLibrary.__init__.body')
        self.body.setFont(QtGui.QFont('Microsoft YaHei', 11))
        self.body.document().setDefaultStyleSheet('p { margin-top: 8px; margin-bottom: 10px; } pre { margin: 10px; }')
        self.body.setOpenExternalLinks(True)
        self.body.document().setBaseUrl(QtCore.QUrl.fromLocalFile(str(ROOT) + '/'))
        self.body.setMinimumHeight(220)
        content.addWidget(self.body, 3)
        row = QtWidgets.QHBoxLayout()
        for title, action in [('上一节', lambda: self.move(-1)), ('下一节', lambda: self.move(1)),
                              ('标记已读', self.mark_read), ('字号＋', lambda: self.body.zoomIn()),
                              ('字号－', lambda: self.body.zoomOut()), ('复制代码', self.copy_code)]:
            button = help_target(QtWidgets.QPushButton(title), 'course_ui.CourseLibrary.__init__.button')
            button.clicked.connect(action)
            row.addWidget(button)
        content.addLayout(row)
        self.lab_panel = QtWidgets.QGroupBox('Python 练习 · 仅运行可信代码，与交易账户独立')
        lab_layout = QtWidgets.QVBoxLayout(self.lab_panel)
        self.examples = help_target(QtWidgets.QComboBox(), 'course_ui.CourseLibrary.__init__.examples')
        lab_layout.addWidget(self.examples)
        self.code = help_target(QtWidgets.QPlainTextEdit(), 'course_ui.CourseLibrary.__init__.code')
        self.code.setFont(QtGui.QFont('Consolas', 11))
        self.code.setMinimumHeight(110)
        self.code.setMaximumHeight(160)
        lab_layout.addWidget(self.code)
        buttons = QtWidgets.QHBoxLayout()
        self.run_button = help_target(QtWidgets.QPushButton('运行练习'), 'course_ui.CourseLibrary.__init__.run_button')
        self.stop_button = help_target(QtWidgets.QPushButton('停止'), 'course_ui.CourseLibrary.__init__.stop_button')
        self.stop_button.setEnabled(False)
        self.reset_button = help_target(QtWidgets.QPushButton('还原本课示例'), 'course_ui.CourseLibrary.__init__.reset_button')
        for button in (self.run_button, self.stop_button, self.reset_button):
            buttons.addWidget(button)
        lab_layout.addLayout(buttons)
        more = QtWidgets.QHBoxLayout()
        self.load_strategy_button = help_target(QtWidgets.QPushButton('载入策略教学副本'), 'course_ui.CourseLibrary.__init__.load_strategy_button')
        self.export_button = help_target(QtWidgets.QPushButton('导出本课 Notebook'), 'course_ui.CourseLibrary.__init__.export_button')
        self.open_export_button = help_target(QtWidgets.QPushButton('打开导出目录'), 'course_ui.CourseLibrary.__init__.open_export_button')
        self.open_export_button.setEnabled(False)
        for button in (self.load_strategy_button, self.export_button, self.open_export_button):
            more.addWidget(button)
        lab_layout.addLayout(more)
        self.export_all_button = help_target(QtWidgets.QPushButton('导出全部课程 Notebook'), 'course_ui.CourseLibrary.__init__.export_all_button')
        lab_layout.addWidget(self.export_all_button)
        self.output = help_target(QtWidgets.QPlainTextEdit(), 'course_ui.CourseLibrary.__init__.output')
        self.output.setReadOnly(True)
        self.output.setMaximumHeight(140)
        lab_layout.addWidget(self.output)
        self.displays = help_target(QtWidgets.QTabWidget(), 'course_ui.CourseLibrary.__init__.displays')
        self.displays.setMaximumHeight(220)
        self.displays.hide()
        lab_layout.addWidget(self.displays)
        content.addWidget(self.lab_panel, 2)
        self.check_panel = QtWidgets.QGroupBox('本课知识自测')
        checks = QtWidgets.QVBoxLayout(self.check_panel)
        self.check_question = QtWidgets.QLabel()
        self.check_question.setWordWrap(True)
        checks.addWidget(self.check_question)
        check_row = QtWidgets.QHBoxLayout()
        self.check_input = help_target(QtWidgets.QLineEdit(), 'course_ui.CourseLibrary.__init__.check_input')
        self.check_input.setPlaceholderText('输入题目要求的数字或简短答案')
        self.check_button = help_target(QtWidgets.QPushButton('检查答案'), 'course_ui.CourseLibrary.__init__.check_button')
        check_row.addWidget(self.check_input, 1)
        check_row.addWidget(self.check_button)
        checks.addLayout(check_row)
        self.check_feedback = QtWidgets.QLabel()
        self.check_feedback.setWordWrap(True)
        checks.addWidget(self.check_feedback)
        content.addWidget(self.check_panel)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(right)
        self.content_scroll = scroll
        split.addWidget(scroll)
        split.setSizes([260, 800])
        layout.addWidget(split)
        self.runner = CourseLab(window.root / 'learning' / 'labs', self)
        self.runner.result.connect(self.receive)
        self.run_button.clicked.connect(self.run)
        self.stop_button.clicked.connect(lambda: self.runner.cancel())
        self.reset_button.clicked.connect(self.reset)
        self.examples.currentIndexChanged.connect(self.select_example)
        self.export_button.clicked.connect(self.export_notebook)
        self.export_all_button.clicked.connect(lambda: self.export_notebook(all_lessons=True))
        self.open_export_button.clicked.connect(self.open_export)
        self.load_strategy_button.clicked.connect(self.load_strategy)
        self.search.textChanged.connect(self.filter)
        self.bookmarks_only.toggled.connect(lambda: self.filter(self.search.text()))
        self.bookmark.clicked.connect(self.toggle_bookmark)
        self.answers.toggled.connect(self.refresh_body)
        self.toc.activated.connect(self.jump_section)
        self.check_button.clicked.connect(self.submit_answer)
        self.tree.currentItemChanged.connect(self.select)
        self.code.textChanged.connect(self.save_draft)
        self.body.verticalScrollBar().valueChanged.connect(self.save_position)
        QtWidgets.QApplication.instance().aboutToQuit.connect(self.shutdown)
        self.populate()

    def persist(self):
        self.window.store.set_setting('learning_library_v1', self.state)

    def populate(self):
        groups = {}
        self.items = []
        for entry in self.entries:
            group = ('操作手册' if entry['kind'] == 'manual' else '量化课程') + ' · ' + entry['module']
            if group not in groups:
                groups[group] = QtWidgets.QTreeWidgetItem(self.tree, [group])
            ready = entry.get('status') == 'published'
            item = QtWidgets.QTreeWidgetItem(groups[group], [entry['title'] + ('' if ready else ' · 待编写')])
            item.setData(0, QtCore.Qt.ItemDataRole.UserRole, entry)
            item.setToolTip(0, entry['title'])
            self.items.append(item)
        self.tree.expandAll()
        last = self.state.get('_last')
        target = next((i for i in self.items if i.data(0, QtCore.Qt.ItemDataRole.UserRole)['id'] == last), self.items[0])
        self.tree.setCurrentItem(target)

    def filter(self, query):
        query = query.strip().casefold()
        for item in self.items:
            entry = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
            item.setHidden(query not in (entry['title'] + entry['module'] + self.texts.get(entry['id'], '')).casefold()
                           or (self.bookmarks_only.isChecked() and not self.state.get(entry['id'], {}).get('bookmark')))
        for index in range(self.tree.topLevelItemCount()):
            parent = self.tree.topLevelItem(index)
            parent.setHidden(all(parent.child(i).isHidden() for i in range(parent.childCount())))

    def select(self, item, previous=None):
        if not item:
            return
        entry = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if not entry:
            return
        self.runner.cancel()
        self.current = None
        self.example = None
        saved = self.state.get(entry['id'], {})
        examples = entry.get('examples', [])
        self.lab_panel.setVisible(bool(examples))
        self.examples.blockSignals(True)
        self.examples.clear()
        for example in examples:
            environment = {'lab': '软件内 Python', 'strategy': '策略编辑器', 'notebook': '外部 Notebook'}[example.get('environment', 'lab')]
            self.examples.addItem(example.get('label', example['id']) + ' · ' + environment, example)
        self.examples.blockSignals(False)
        self.output.clear()
        self.clear_displays()
        self.current = entry
        self.refresh_body()
        self.bookmark.setText('移除书签' if saved.get('bookmark') else '添加书签')
        self.check_panel.setVisible(bool(entry.get('check')))
        self.check_question.setText(entry.get('check', {}).get('question', ''))
        self.check_input.clear()
        self.check_feedback.setText('本版知识自测已通过。' if entry.get('status') == 'published'
                                   and saved.get('check_digest') == digest(entry) else '')
        self.select_example()
        self.state['_last'] = entry['id']
        self.persist()
        changed = saved.get('read_digest') and saved['read_digest'] != digest(entry) if entry.get('status') == 'published' else False
        self.status.setText('正文已更新，建议复习。' if changed else
                            '本课已读，可继续练习。' if saved.get('read_digest') else '阅读、代码练习与知识自测分别记录。')
        identity = entry['id']
        # The reader can be destroyed before the queued layout/scroll restore runs.
        # Bind the callback to its QObject so Qt cancels it with the text browser.
        QtCore.QTimer.singleShot(0, self.body, lambda: self.body.verticalScrollBar().setValue(saved.get('position', 0))
                                 if self.current and self.current['id'] == identity else None)

    def refresh_body(self, *_):
        if not self.current:
            return
        position = self.body.verticalScrollBar().value()
        text, _ = sections(self.texts.get(self.current['id'], '# ' + self.current['title'] + '\n\n本课尚未编写。'), self.answers.isChecked())
        scrollbar = self.body.verticalScrollBar()
        scrollbar.blockSignals(True)
        self.body.setMarkdown(text)
        block = self.body.document().begin()
        image_formats = []
        while block.isValid():
            iterator = block.begin()
            while not iterator.atEnd():
                fragment = iterator.fragment()
                if fragment.isValid() and fragment.charFormat().isImageFormat():
                    image_formats.append((fragment.position(), fragment.charFormat().toImageFormat()))
                iterator += 1
            block = block.next()
        for at, image_format in image_formats:
            picture = self.body.document().resource(QtGui.QTextDocument.ResourceType.ImageResource, QtCore.QUrl(image_format.name()))
            if picture is not None and not picture.isNull() and picture.width() > 640:
                image_format.setWidth(640)
                image_format.setHeight(picture.height() * 640 / picture.width())
                cursor = QtGui.QTextCursor(self.body.document())
                cursor.setPosition(at)
                cursor.movePosition(QtGui.QTextCursor.MoveOperation.NextCharacter, QtGui.QTextCursor.MoveMode.KeepAnchor)
                cursor.setCharFormat(image_format)
        self.toc.clear()
        block = self.body.document().begin()
        while block.isValid():
            if block.blockFormat().headingLevel():
                self.toc.addItem(block.text(), block.position())
            block = block.next()
        scrollbar.setValue(position)
        scrollbar.blockSignals(False)

    def jump_section(self, index):
        position = self.toc.itemData(index)
        if position is not None:
            cursor = QtGui.QTextCursor(self.body.document())
            cursor.setPosition(position)
            self.body.setTextCursor(cursor)
            self.body.ensureCursorVisible()

    def toggle_bookmark(self):
        if self.current:
            state = self.state.setdefault(self.current['id'], {})
            state['bookmark'] = not state.get('bookmark', False)
            self.bookmark.setText('移除书签' if state['bookmark'] else '添加书签')
            self.persist()
            self.filter(self.search.text())

    def submit_answer(self):
        if not self.current or not self.current.get('check'):
            return
        check = self.current['check']
        passed = check_answer(check, self.check_input.text())
        if passed:
            self.state.setdefault(self.current['id'], {})['check_digest'] = digest(self.current)
            self.persist()
        self.check_feedback.setText(('回答正确。' + check['explanation']) if passed else '尚未答对。按题目指定单位作答，并回到相关公式或示例核对。')

    def save_draft(self):
        if self.current and self.example:
            self.state.setdefault(self.current['id'], {}).setdefault('drafts', {})[self.example['id']] = self.code.toPlainText()
            self.persist()

    def select_example(self, *_):
        self.runner.cancel()
        self.example = None
        selected = self.examples.currentData()
        if not self.current or not selected:
            self.code.clear()
            return
        saved = self.state.get(self.current['id'], {})
        initial = resource(selected['file']).read_text(encoding='utf-8')
        legacy = saved.get('draft', initial) if self.examples.currentIndex() == 0 else initial
        self.code.setPlainText(saved.get('drafts', {}).get(selected['id'], legacy))
        self.example = selected
        environment = selected.get('environment', 'lab')
        self.run_button.setEnabled(environment == 'lab')
        self.load_strategy_button.setVisible(environment == 'strategy')
        self.run_button.setToolTip('普通 Python 在软件内运行；策略在编辑器执行，进阶课导出 Notebook。')

    def export_notebook(self, checked=False, *, all_lessons=False):
        if not self.current or self.current.get('status') != 'published':
            return
        from astock.course_notebooks import export_notebooks
        try:
            self.exported_path = export_notebooks(self.window.root / 'learning' / 'notebooks', None if all_lessons else [self.current])
            self.open_export_button.setEnabled(True)
            self.status.setText('已导出课程原始代码（练习区草稿另行保留）：' + str(self.exported_path)
                                + '。用 PowerShell 7 运行其中 Start-Notebook.ps1；首次安装需要联网。')
        except Exception as error:
            self.status.setText('导出失败：' + str(error))

    def open_export(self):
        if self.exported_path:
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(self.exported_path)))

    def load_strategy(self):
        if not self.example or self.example.get('environment') != 'strategy':
            return
        import uuid
        from astock.strategy import parameter_schema
        code = self.code.toPlainText()
        try:
            parameter_schema(code)
            w = self.window
            w.save_strategy(quiet=True)
            w.current_template = '课程 · ' + self.current['title'] + ' ' + uuid.uuid4().hex[:6]
            w.strategy_title.setText(w.current_template)
            w.editor.setPlainText(code)
            w.rebuild_parameters()
            w.save_strategy(quiet=True)
            w.refresh_library()
            w.open_strategy_editor()
        except Exception as error:
            self.status.setText('无法载入教学副本：' + str(error))

    def save_position(self, value):
        if self.current:
            self.state.setdefault(self.current['id'], {})['position'] = value
            self.persist()

    def mark_read(self):
        if self.current and self.current.get('status') == 'published':
            self.state.setdefault(self.current['id'], {})['read_digest'] = digest(self.current)
            self.persist()
            self.status.setText('已记录阅读；未代替答题或实作。')

    def move(self, direction):
        visible = [i for i in self.items if not i.isHidden()]
        item = self.tree.currentItem()
        if item in visible:
            index = visible.index(item) + direction
            if 0 <= index < len(visible):
                self.tree.setCurrentItem(visible[index])

    def copy_code(self):
        QtWidgets.QApplication.clipboard().setText(self.code.toPlainText())

    def reset(self):
        if self.current and self.example:
            if QtWidgets.QMessageBox.question(self, '还原示例', '用本课原始代码替换练习区草稿？') == QtWidgets.QMessageBox.StandardButton.Yes:
                self.code.setPlainText(resource(self.example['file']).read_text(encoding='utf-8'))

    def run(self):
        if not self.current or not self.example or self.example.get('environment', 'lab') != 'lab':
            return
        self.output.setPlainText('运行中…')
        self.clear_displays()
        try:
            self.active = self.runner.start(self.current['id'], self.code.toPlainText())
            self.run_button.setEnabled(False)
            self.stop_button.setEnabled(True)
        except Exception as error:
            self.output.setPlainText(str(error))

    def receive(self, result):
        if result['token'] != self.active:
            return
        self.active = None
        self.run_button.setEnabled(bool(self.example and self.example.get('environment', 'lab') == 'lab'))
        self.stop_button.setEnabled(False)
        self.output.setPlainText(result.get('output', '') + '\n' + result.get('error', ''))
        self.render_displays(result.get('displays', []))
        self.content_scroll.ensureWidgetVisible(self.output)
        saved = self.state.setdefault(result['exercise_id'], {})
        saved['last_run_status'] = result['status']
        self.persist()
        self.status.setText('代码运行成功，不代表答案已验证。' if result['status'] == 'finished' else '本次练习未完成：' + result['status'])

    def clear_displays(self):
        while self.displays.count():
            widget = self.displays.widget(0)
            self.displays.removeTab(0)
            widget.deleteLater()
        self.displays.hide()

    def render_displays(self, displays):
        self.clear_displays()
        for value in displays:
            if value['kind'] == 'table':
                widget = help_target(QtWidgets.QTableWidget(len(value['rows']), len(value['headers'])), 'course_ui.CourseLibrary.render_displays.widget')
                widget.setHorizontalHeaderLabels(value['headers'])
                widget.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
                for row, cells in enumerate(value['rows']):
                    for col, text in enumerate(cells[:len(value['headers'])]):
                        widget.setItem(row, col, QtWidgets.QTableWidgetItem(text))
            else:
                import pyqtgraph as pg
                widget = help_target(pg.PlotWidget(), 'course_ui.CourseLibrary.render_displays.widget2')
                widget.addLegend()
                widget.setLabel('bottom', '观察序号')
                for index, (name, points) in enumerate(value['series'].items()):
                    values = [float('nan') if p is None else p for p in points]
                    color = pg.intColor(index, hues=max(4, len(value['series'])))
                    if value['kind'] == 'bars':
                        widget.addItem(pg.BarGraphItem(x=list(range(len(values))), height=values, width=.65, brush=color))
                    else:
                        widget.plot(values, pen=pg.mkPen(color, width=2), name=name, connect='finite')
            label = value['title'] + ('（展示已截断）' if value.get('truncated') else '')
            self.displays.addTab(widget, label)
        self.displays.setVisible(bool(displays))

    def shutdown(self):
        self.runner.close()
