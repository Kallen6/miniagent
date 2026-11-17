"""任务持久化：/api/v1 异步任务的 SQLite 存取层。

设计要点：
- 单文件库 agent/data/tasks.db，进程重启后任务历史不丢；
- 单连接 + threading.RLock：事件循环线程与工具工作线程都会读写，靠锁串行化；
- steps 以 JSON 数组整体读改写（任务步骤量小，UPSERT 语义足够，避免逐条建表）；
- 清理策略只删终态任务（succeeded/failed/cancelled），不会误删 running 中的任务。
"""
import json
import sqlite3
import threading
import time
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "tasks.db"

# 终态集合：进入终态的任务不再变更，可被清理
TERMINAL_STATUSES = {"succeeded", "failed", "cancelled"}


class TaskStore:
    """SQLite 任务表封装：create / get / set_status / append_step / cleanup。"""

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path) if db_path else DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init_table()

    def _init_table(self) -> None:
        with self._lock:
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id      TEXT PRIMARY KEY,
                    status  TEXT NOT NULL,
                    created REAL NOT NULL,
                    updated REAL NOT NULL,
                    result  TEXT,
                    error   TEXT,
                    steps   TEXT NOT NULL DEFAULT '[]'
                )
            """)
            self._conn.commit()

    def create(self, task_id: str) -> None:
        now = time.time()
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO tasks (id, status, created, updated, result, error, steps) "
                "VALUES (?, 'queued', ?, ?, NULL, NULL, '[]')",
                (task_id, now, now),
            )
            self._conn.commit()

    def get(self, task_id: str) -> dict | None:
        """返回任务 dict（steps 已反序列化）；不存在返回 None。"""
        with self._lock:
            row = self._conn.execute(
                "SELECT id, status, created, result, error, steps FROM tasks WHERE id = ?",
                (task_id,),
            ).fetchone()
        if row is None:
            return None
        try:
            steps = json.loads(row[5])
        except (TypeError, ValueError):
            steps = []
        return {
            "id": row[0], "status": row[1], "created": row[2],
            "result": row[3], "error": row[4], "steps": steps,
        }

    def set_status(
        self,
        task_id: str,
        status: str,
        result: str | None = None,
        error: str | None = None,
    ) -> None:
        """更新任务状态；仅进入终态时写入 result/error（运行态变更不覆盖结果字段）。"""
        with self._lock:
            if status in TERMINAL_STATUSES:
                self._conn.execute(
                    "UPDATE tasks SET status = ?, updated = ?, "
                    "result = COALESCE(?, result), error = COALESCE(?, error) WHERE id = ?",
                    (status, time.time(), result, error, task_id),
                )
            else:
                self._conn.execute(
                    "UPDATE tasks SET status = ?, updated = ? WHERE id = ?",
                    (status, time.time(), task_id),
                )
            self._conn.commit()

    def append_step(self, task_id: str, step: dict) -> None:
        """向任务追加一条执行步骤（AgentStep.to_dict()）。"""
        with self._lock:
            row = self._conn.execute(
                "SELECT steps FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
            if row is None:
                return
            try:
                steps = json.loads(row[0])
            except (TypeError, ValueError):
                steps = []
            steps.append(step)
            self._conn.execute(
                "UPDATE tasks SET steps = ?, updated = ? WHERE id = ?",
                (json.dumps(steps, ensure_ascii=False), time.time(), task_id),
            )
            self._conn.commit()

    def cleanup(self, keep: int = 200) -> None:
        """淘汰最旧的终态任务至 keep 条以内；绝不删除 running/queued 任务。"""
        with self._lock:
            self._conn.execute(
                "DELETE FROM tasks WHERE status IN (?, ?, ?) AND id NOT IN ("
                "  SELECT id FROM tasks WHERE status IN (?, ?, ?)"
                "  ORDER BY updated DESC, rowid DESC LIMIT ?"
                ")",
                (*TERMINAL_STATUSES, *TERMINAL_STATUSES, keep),
            )
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()
