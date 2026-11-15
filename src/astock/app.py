from __future__ import annotations

import argparse
import multiprocessing as mp
import os
from pathlib import Path
import sys


def main():
    from astock.runtime import ensure_standard_streams
    ensure_standard_streams()
    mp.freeze_support()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="AStock 量化研究与仿真工作台")
    parser.add_argument("--data-dir", help="覆盖本机数据目录")
    parser.add_argument("--isolated-instance", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--smoke", action="store_true", help="执行完整桌面回测冒烟测试并退出")
    parser.add_argument("--smoke-mode", choices=("backtest", "replay", "equity"), default="backtest",
                        help="桌面冒烟测试使用日线回测、快照回放或权益教学")
    parser.add_argument("--screenshot", help="保存界面截图，供视觉核验")
    parser.add_argument("--width", type=int, default=1480)
    parser.add_argument("--height", type=int, default=940)
    parser.add_argument("--theme", choices=("dark", "light"))
    parser.add_argument("--probe", action="store_true", help="只读行情连通性探测")
    parser.add_argument("--catalog-smoke", action="store_true", help="证券搜索窗口验收并退出")
    parser.add_argument("--catalog-refresh", action="store_true", help="目录验收时实际更新公开证券资料")
    parser.add_argument("--quality-smoke", action="store_true", help="数据中心缺口检查窗口验收并退出")
    parser.add_argument("--rules-smoke", action="store_true", help="证券规则修订及日期边界回测验收并退出")
    parser.add_argument("--minute-smoke", action="store_true", help="真实分钟行情下载与桌面回测验收并退出（需要网络）")
    parser.add_argument("--status-smoke", action="store_true", help="真实历史状态获取、修订及回测验收（需要网络）")
    parser.add_argument("--live-rules-smoke", action="store_true", help="当日 ETF 规则与实时账户操作验收（需要网络）")
    parser.add_argument("--operations-smoke", action="store_true", help="后台报告、运行对比和录制整理验收并退出")
    parser.add_argument("--learning-smoke", action="store_true", help="四课互动学习流程验收并退出")
    parser.add_argument('--course-smoke', action='store_true', help='长期课程、帮助、隔离练习及 Notebook 导出验收并退出')
    parser.add_argument("--learning-online", action="store_true", help="四课验收附加真实行情连接与虚拟账户启停")
    parser.add_argument("--quality-dataset", help="缺口验收使用的已有数据集；不指定则用明确标注的合成数据")
    parser.add_argument("--live-check-minutes", type=float, default=0, help="连续采集并生成独立行情验收报告")
    args = parser.parse_args()
    if args.data_dir:
        os.environ["ASTOCK_DATA_DIR"] = str(Path(args.data_dir).resolve())
    from astock.storage import user_root
    root = user_root()
    if args.probe or args.live_check_minutes:
        from astock.validation import validate_market
        result = validate_market(root, args.live_check_minutes)
        print(result)
        return
    from PySide6 import QtCore, QtGui, QtWidgets
    import pyqtgraph as pg
    from astock.window import MainWindow

    if sys.platform == "win32":
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("AStock.Workbench")
    QtWidgets.QApplication.setHighDpiScaleFactorRoundingPolicy(
        QtCore.Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    application = QtWidgets.QApplication(sys.argv[:1])
    application.setApplicationName("AStock")
    application.setOrganizationName("AStock")
    resource_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    application.setWindowIcon(QtGui.QIcon(str(resource_root / "assets" / "astock.ico")))
    application.setFont(QtGui.QFont("Microsoft YaHei UI", 9))
    from astock.single_instance import InstanceGuard
    # Normal launchers may specify --data-dir and must still share the user lock.
    # Only explicit test isolation and validation runs use the data lock alone.
    isolated = bool(args.isolated_instance or args.screenshot or any(
        value for key, value in vars(args).items() if key.endswith('_smoke')) or args.smoke)
    instance_guard = InstanceGuard(root, global_scope=not isolated)
    try:
        if not instance_guard.acquire():
            return
    except RuntimeError as error:
        QtWidgets.QMessageBox.critical(None, '无法启动 AStock', str(error))
        sys.exit(2)
    pg.setConfigOptions(antialias=True, useOpenGL=False)
    window = MainWindow(root, start_workers=not args.course_smoke)
    instance_guard.set_window(window)
    if args.theme:
        window.theme_name = args.theme
        window.apply_theme()
    if args.screenshot:
        window.fit_initial_layout(args.width, args.height)
    else:
        available = application.primaryScreen().availableGeometry()
        window.fit_initial_layout(min(args.width, available.width() - 24), min(args.height, available.height() - 45))
    window.show()
    # 供命令行和打包验收使用；不用截图来替代引擎正确性测试。
    if args.course_smoke:
        from astock.course_validation import start_course_smoke
        timer = start_course_smoke(application, window, args.screenshot)
    elif args.live_rules_smoke:
        from astock.live_rule_validation import start_live_rule_smoke
        timer = start_live_rule_smoke(application, window, args.screenshot)
    elif args.status_smoke:
        from astock.status_validation import start_status_smoke
        timer = start_status_smoke(application, window, args.screenshot)
    elif args.minute_smoke:
        from astock.minute_validation import start_minute_smoke
        timer = start_minute_smoke(application, window, args.screenshot)
    elif args.rules_smoke:
        from astock.rule_validation import start_rule_smoke
        timer = start_rule_smoke(application, window, args.screenshot)
    elif args.learning_smoke:
        from astock.learning_validation import start_learning_smoke
        timer = start_learning_smoke(application, window, args.screenshot, args.learning_online)
    elif args.operations_smoke:
        from astock.operations_validation import start_operations_smoke
        timer = start_operations_smoke(application, window, args.screenshot)
    elif args.quality_smoke:
        from astock.quality_validation import start_quality_smoke
        timer = start_quality_smoke(application, window, args.screenshot, args.quality_dataset)
    elif args.catalog_smoke:
        from astock.catalog_validation import start_catalog_smoke
        timer = start_catalog_smoke(application, window, args.screenshot, args.catalog_refresh)
    elif args.smoke:
        import time
        started = time.monotonic()
        marker = {"started": False, "done": False}
        def smoke_poll():
            if not marker["started"] and time.monotonic() - started > 1:
                marker["started"] = True
                if args.smoke_mode == "equity":
                    window.prepare_equity_lesson()
                else:
                    window._select_demo("quote" if args.smoke_mode == "replay" else "bar")
                window.speed_combo.setCurrentIndex(window.speed_combo.findData(1000))
                window.start_run()
            state = window.states.get(window.active_id)
            if (state and state["status"] in ("COMPLETED", "ERROR") and not marker["done"]
                    and window.preview_token is None):
                marker["done"] = True
                from astock.domain import dumps
                from astock.reports import export_report
                output = Path(args.screenshot).parent if args.screenshot else root / "reports"
                output.mkdir(parents=True, exist_ok=True)
                (output / "smoke-result.json").write_text(dumps({
                    "status": state["status"], "mode": state["mode"], "statistics": state["result"]["statistics"],
                    "orders": len(state["snapshot"]["orders"]), "trades": len(state["snapshot"]["trades"]),
                    "engine_alive": all(p.is_alive() for p in window.processes),
                    "window": [window.width(), window.height()],
                    "device_pixel_ratio": window.devicePixelRatioF(),
                    "preview_rows": len(window.preview_chart.points),
                    "preview_ready": bool(window.preview_chart.points) and window.preview_identity == state["manifest"]["dataset"]["id"],
                    "trade_rows": window.trades_table.model().rowCount(),
                    "equity_rows": window.equity_table.model().rowCount(),
                    "equity_entries": len(state["snapshot"].get("equity_entries", [])),
                    "available_positions": state.get("available_positions", {}),
                }), encoding="utf-8")
                export_report(root, state)
                if args.screenshot:
                    # Native high-DPI axis sizing completes after the data update.
                    QtCore.QTimer.singleShot(1800, lambda: window.grab().save(args.screenshot))
                    QtCore.QTimer.singleShot(1900, lambda: window.bottom_tabs.setCurrentIndex(2))
                    QtCore.QTimer.singleShot(2050, lambda: window.grab().save(str(output / "trades.png")))
                    QtCore.QTimer.singleShot(2150, lambda: window.trades_table.selectRow(0))
                    QtCore.QTimer.singleShot(2350, lambda: window.grab().save(str(output / "trade-detail.png")))
                    QtCore.QTimer.singleShot(2450, lambda: window.switch_workspace(0))
                    QtCore.QTimer.singleShot(2600, lambda: window.grab().save(str(output / "research.png")))
                    QtCore.QTimer.singleShot(2750, lambda: window.switch_workspace(3))
                    QtCore.QTimer.singleShot(2900, lambda: window.grab().save(str(output / "learning.png")))
                    QtCore.QTimer.singleShot(3000, lambda: (window.switch_workspace(1), window.bottom_tabs.setCurrentIndex(4)))
                    QtCore.QTimer.singleShot(3150, lambda: window.grab().save(str(output / "equity.png")))
                exit_code = 0 if (state["status"] == "COMPLETED" and state["snapshot"]["trades"]
                                  and window.preview_chart.points) else 2
                if args.smoke_mode == "equity" and (len(state["snapshot"].get("equity_entries", [])) != 2
                        or state["result"]["statistics"]["dividends_paid"] != 100):
                    exit_code = 2
                QtCore.QTimer.singleShot(3400 if args.screenshot else 700,
                                        lambda: (window.close(), application.exit(exit_code)))
            if time.monotonic() - started > 90 and not marker["done"]:
                marker["done"] = True
                window.close()
                application.exit(3)
        timer = QtCore.QTimer(application)
        timer.timeout.connect(smoke_poll)
        timer.start(200)
    elif args.screenshot:
        def capture():
            Path(args.screenshot).parent.mkdir(parents=True, exist_ok=True)
            window.grab().save(args.screenshot)
            window.close()
        QtCore.QTimer.singleShot(1800, capture)
    else:
        from astock.onboarding import open_onboarding
        QtCore.QTimer.singleShot(450, lambda w=window: open_onboarding(w, first_run=True))
    exit_code = application.exec()
    while getattr(window, 'reset_requested', False):
        from astock.app_reset import initialize_closed_data
        try:
            if any(process.is_alive() for process in window.processes):
                raise RuntimeError('后台引擎未退出，初始化已停止。请关闭应用后重试。')
            if window.history_process and window.history_process.is_alive():
                raise RuntimeError('数据下载尚未退出，初始化已停止。')
            if any(process.is_alive() for process in mp.active_children()):
                raise RuntimeError('仍有后台任务未退出，初始化已停止。请关闭应用后重试。')
            initialize_closed_data(root)
        except Exception as error:
            QtWidgets.QMessageBox.critical(None, '初始化未完成', str(error))
            sys.exit(2)
        window.deleteLater()
        window = MainWindow(root)
        instance_guard.set_window(window)
        available = application.primaryScreen().availableGeometry()
        window.fit_initial_layout(min(args.width, available.width() - 24),
                                  min(args.height, available.height() - 45))
        window.show()
        window.statusBar().showMessage('初始化完成 · 学习进度已保留，其他本地数据已清空 · 未创建备份')
        from astock.onboarding import open_onboarding
        QtCore.QTimer.singleShot(450, lambda w=window: open_onboarding(w, first_run=True))
        exit_code = application.exec()
    instance_guard.close()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
