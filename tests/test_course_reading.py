from types import SimpleNamespace
from PySide6 import QtCore
from astock.course_reading import sections, check_answer
from astock.course_ui import CourseLibrary
from astock.storage import Store


def test_qt_markdown_preserves_published_chinese_text(qtbot):
    import re
    from PySide6 import QtWidgets
    from astock.course_library import catalogue, article
    browser = QtWidgets.QTextBrowser()
    qtbot.addWidget(browser)
    for entry in catalogue():
        if entry.get('status') != 'published':
            continue
        text = article(entry)
        browser.setMarkdown(sections(text, True)[0])
        before = len(re.findall(r'[\u4e00-\u9fff]', text))
        after = len(re.findall(r'[\u4e00-\u9fff]', browser.toPlainText()))
        assert after >= before * .9, entry['id']


def test_hidden_answers_keep_code_headings_and_navigation_intact():
    text = '# 课程\n## 练习\n先想一想\n```python\n# 答案不是标题\nx = 1\n```\n## 参考答案\n答案内容\n## 延伸\n继续学习'
    hidden, headings = sections(text)
    assert '答案内容' not in hidden and '继续学习' in hidden and '# 答案不是标题' in hidden
    assert len(headings) == 4
    assert '答案内容' in sections(text, True)[0]
    assert check_answer({'answers': ['true', '对']}, 'ＴＲＵＥ。')
    assert not check_answer({'answers': ['true']}, '')
    assert check_answer({'answers': ['2']}, '２.００')
    assert not check_answer({'answers': ['2']}, 'NaN')


def test_bookmarks_checks_and_positions_are_separate_from_legacy_progress(qtbot, tmp_path):
    store = Store(tmp_path)
    store.set_setting('learning_progress', {'sentinel': 'retain'})
    reader = CourseLibrary(SimpleNamespace(root=tmp_path, store=store))
    qtbot.addWidget(reader)
    reader.resize(900, 650)
    reader.show()
    reader.texts['q01'] = '# 测试长文\n\n' + '\n\n'.join('阅读位置测试段落 ' + str(i) for i in range(100)) + '\n\n## 终点\n\n最后一节'
    item = next(i for i in reader.items if i.data(0, QtCore.Qt.ItemDataRole.UserRole)['id'] == 'q01')
    reader.tree.setCurrentItem(item)
    reader.refresh_body()
    qtbot.wait(30)
    reader.toc.activated.emit(1)
    assert reader.body.verticalScrollBar().value() > 0
    reader.current['check'] = {'question': '1+1?', 'answers': ['2'], 'explanation': '加法。'}
    reader.check_input.setText('3')
    reader.submit_answer()
    assert 'check_digest' not in reader.state.get('q01', {})
    reader.check_input.setText('2')
    reader.submit_answer()
    assert reader.state['q01']['check_digest']
    reader.toggle_bookmark()
    reader.bookmarks_only.setChecked(True)
    assert sum(not i.isHidden() for i in reader.items) == 1
    reader.body.verticalScrollBar().setValue(100)
    saved = reader.state['q01']['position']
    reader.tree.setCurrentItem(reader.items[-1])
    reader.tree.setCurrentItem(item)
    qtbot.wait(20)
    assert reader.body.verticalScrollBar().value() == saved
    assert store.setting('learning_progress') == {'sentinel': 'retain'}
    reader.shutdown()
    reader.close()
    store.close()
