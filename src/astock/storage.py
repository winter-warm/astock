from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

from astock.domain import dumps, loads, now_cn


def user_root() -> Path:
    override = os.environ.get("ASTOCK_DATA_DIR")
    if override:
        return Path(override).resolve()
    if getattr(sys, "frozen", False):
        portable = Path(sys.executable).parent / "portable.flag"
        if portable.exists():
            return portable.parent / "data"
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "AStock"


class Store:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        for name in ("datasets", "strategies", "reports", "logs"):
            (self.root / name).mkdir(exist_ok=True)
        self.db = sqlite3.connect(self.root / "workbench.sqlite3", timeout=10)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS runs(
                id TEXT PRIMARY KEY, name TEXT NOT NULL, mode TEXT NOT NULL,
                status TEXT NOT NULL, created TEXT NOT NULL, manifest TEXT NOT NULL,
                snapshot TEXT NOT NULL, result TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS journals(
                id INTEGER PRIMARY KEY, run_id TEXT NOT NULL, time TEXT NOT NULL,
                kind TEXT NOT NULL, payload TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS journals_run ON journals(run_id, id);
            CREATE TABLE IF NOT EXISTS strategies(
                name TEXT PRIMARY KEY, code TEXT NOT NULL, parameters TEXT NOT NULL, modified TEXT NOT NULL);
            PRAGMA user_version=1;
        """)

    def setting(self, key, default=None):
        row = self.db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return loads(row[0]) if row else default

    def set_setting(self, key, value):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", (key, dumps(value)))

    def save_strategy(self, name, code, parameters):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO strategies VALUES (?,?,?,?)",
                            (name, code, dumps(parameters), now_cn().isoformat()))

    def strategies(self):
        return [{"name": r[0], "code": r[1], "parameters": loads(r[2])} for r in self.db.execute(
            "SELECT name,code,parameters FROM strategies ORDER BY modified DESC")]

    def save_run(self, run_id, name, mode, status, manifest, snapshot, result, journal=None):
        with self.db:
            self.db.execute("""INSERT INTO runs VALUES (?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET status=excluded.status, snapshot=excluded.snapshot,
                result=excluded.result, manifest=excluded.manifest""",
                            (run_id, name, mode, status, now_cn().isoformat(), dumps(manifest),
                             dumps(snapshot), dumps(result)))
            for kind, payload in journal or []:
                self.db.execute("INSERT INTO journals(run_id,time,kind,payload) VALUES (?,?,?,?)",
                                (run_id, now_cn().isoformat(), kind, dumps(payload)))

    def runs(self):
        return [{"id": r[0], "name": r[1], "mode": r[2], "status": r[3], "created": r[4]}
                for r in self.db.execute("SELECT id,name,mode,status,created FROM runs ORDER BY created DESC")]

    def load_run(self, run_id):
        row = self.db.execute("SELECT manifest,snapshot,result FROM runs WHERE id=?", (run_id,)).fetchone()
        if not row:
            raise ValueError("运行记录不存在")
        return dict(zip(("manifest", "snapshot", "result"), map(loads, row)))

    def close(self):
        self.db.close()
