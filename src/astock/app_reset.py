"""Explicit, backup-free initialization of a closed AStock data directory."""
from pathlib import Path
import os
import shutil
import sqlite3

from PySide6 import QtWidgets


LEARNING_KEYS = ('learning_library_v1', 'course_practice_v1', 'qmt_course_v1', 'lessons_completed')
DATABASE = 'workbench.sqlite3'


def confirm_initialization(window):
    dialog = QtWidgets.QMessageBox(window)
    dialog.setWindowTitle('初始化应用')
    dialog.setIcon(QtWidgets.QMessageBox.Icon.Warning)
    dialog.setText('清空本机应用数据，保留学习进度？')
    dialog.setInformativeText(
        '将停止正在运行的任务，并永久删除策略、虚拟账户、运行记录、行情数据、报告和设置。\n\n'
        '保留：课程阅读进度、自测结果、书签、练习草稿，以及已导出的课程 Notebook。\n'
        '不创建备份，删除后不能在应用内恢复。初始化后重新打开使用教程。\n\n'
        '数据目录：' + str(window.root))
    confirm = dialog.addButton('初始化（不备份）', QtWidgets.QMessageBox.ButtonRole.DestructiveRole)
    cancel = dialog.addButton('取消', QtWidgets.QMessageBox.ButtonRole.RejectRole)
    dialog.setDefaultButton(cancel)
    dialog.setEscapeButton(cancel)
    dialog.exec()
    return dialog.clickedButton() is confirm


def _is_link(path):
    return path.is_symlink() or (hasattr(os.path, 'isjunction') and os.path.isjunction(path))


def _validated_root(root):
    candidate = Path(root).absolute()
    if any(_is_link(p) for p in (candidate, *candidate.parents)):
        raise ValueError('数据目录经过链接或目录联接，不能初始化。')
    resolved = candidate.resolve(strict=True)
    if resolved == Path(resolved.anchor) or resolved == Path.home().resolve():
        raise ValueError('拒绝初始化系统或用户根目录。')
    if any((resolved / name).exists() for name in ('.git', 'pyproject.toml', 'AStock.exe', 'portable.flag')):
        raise ValueError('所选目录包含程序或源码，请使用独立的应用数据目录。')
    database = resolved / DATABASE
    if not database.is_file() or _is_link(database):
        raise ValueError('没有找到独立的 AStock 数据库，不能初始化。')
    return resolved


def _remove_inside(path, root):
    # Check the lexical parent before touching links; never resolve a link target.
    if path.parent.resolve() != root:
        raise ValueError('删除目标不在应用数据目录内。')
    if _is_link(path):
        if path.is_symlink():
            path.unlink()
        else:
            os.rmdir(path)  # Remove the junction itself; do not traverse its target.
    elif path.is_dir():
        # shutil.rmtree on supported Python 3.12 does not follow symlinks/junctions.
        shutil.rmtree(path)
    else:
        path.unlink()


def initialize_closed_data(root):
    """Run only after all workers and Store connections have closed.

    Learning state stays in the same database and learning directory. No copies,
    snapshots or backup directories are made. Failure propagates to the caller.
    """
    root = _validated_root(root)
    database = root / DATABASE
    connection = sqlite3.connect(database, timeout=0)
    removed = []
    deletion_started = False
    try:
        tables = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'settings', 'strategies', 'runs', 'journals'} <= tables:
            raise ValueError('数据库结构不属于 AStock，不能初始化。')
        # Acquire the writer lock before deleting any files. A surviving writer
        # is a shutdown error, not permission to reset concurrently.
        connection.execute('BEGIN EXCLUSIVE')
        placeholders = ','.join('?' for _ in LEARNING_KEYS)
        retained = dict(connection.execute(
            f'SELECT key,value FROM settings WHERE key IN ({placeholders})', LEARNING_KEYS))
        for path in tuple(root.iterdir()):
            if path.name in (DATABASE, DATABASE + '-wal', DATABASE + '-shm', 'learning'):
                continue
            deletion_started = True
            _remove_inside(path, root)
            removed.append(path.name)
        connection.execute('DELETE FROM journals')
        connection.execute('DELETE FROM runs')
        connection.execute('DELETE FROM strategies')
        connection.execute(f'DELETE FROM settings WHERE key NOT IN ({placeholders})', LEARNING_KEYS)
        connection.commit()
        connection.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        return {'removed': sorted(removed), 'retained_learning_keys': sorted(retained), 'backup_created': False}
    except Exception as error:
        connection.rollback()
        if deletion_started:
            raise RuntimeError('初始化未完成；部分非学习文件可能已删除，未创建备份。'
                               '学习进度仍保留。请关闭占用文件的程序后重试。\n' + str(error)) from error
        raise
    finally:
        connection.close()
