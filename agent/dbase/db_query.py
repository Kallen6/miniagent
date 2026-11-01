"""通用数据库查询工具：db_url + 表名 + 字段 + 等值过滤，全部通过传参控制。"""
import json

from sqlalchemy import MetaData, Table, create_engine, select
from sqlalchemy.exc import NoSuchTableError

from ..agent_tools.build_tools import tool

DEFAULT_LIMIT = 50
MAX_LIMIT = 200


def _select_table(engine, table: str):
    """仅反射目标表；表不存在时返回错误提示而非抛异常。"""
    metadata = MetaData()
    try:
        return Table(table, metadata, autoload_with=engine)
    except NoSuchTableError:
        return None


@tool(
    description="通用数据库查询工具：指定数据库连接串、表名、字段与等值过滤条件执行查询，返回 JSON 结果",
    param_descriptions={
        "db_url": "SQLAlchemy 数据库连接串，例如 sqlite:///./test.db 或 mysql+pymysql://user:pwd@host/db",
        "table": "要查询的表名",
        "fields": "要返回的字段名列表，不传则返回全部字段，例如 [\"name\", \"age\"]",
        "filters": "等值过滤条件，键为字段名、值为字段值，例如 {\"age\": 20}",
        "limit": "返回的最大行数，默认 50，最大 200",
    },
)
def query_database(
    db_url: str,
    table: str,
    fields: list = None,
    filters: dict = None,
    limit: int = DEFAULT_LIMIT,
) -> str:
    """按传参查询任意数据库的指定表指定字段，返回 JSON 字符串。

    安全策略：表名/字段名与反射元数据严格匹配，不拼接用户输入；
    过滤值由 SQLAlchemy 参数绑定；结果行数受限。
    """
    try:
        limit = max(1, min(int(limit), MAX_LIMIT))
        engine = create_engine(db_url)
        try:
            tbl = _select_table(engine, table)
            if tbl is None:
                return f"错误：表 {table} 不存在或无法访问"
            columns = list(tbl.columns.keys())

            if fields:
                invalid = [f for f in fields if f not in columns]
                if invalid:
                    return f"错误：字段不存在 {invalid}，可用字段 {columns}"
                selected = [tbl.c[f] for f in fields]
            else:
                selected = [tbl.c[c] for c in columns]

            stmt = select(*selected).limit(limit)

            if filters:
                invalid = [k for k in filters if k not in columns]
                if invalid:
                    return f"错误：过滤字段不存在 {invalid}，可用字段 {columns}"
                for key, value in filters.items():
                    stmt = stmt.where(tbl.c[key] == value)  # 值由参数绑定，防注入

            with engine.connect() as conn:
                rows = [list(row) for row in conn.execute(stmt).fetchall()]

            return json.dumps(
                {
                    "table": table,
                    "columns": [c.name for c in selected],
                    "rows": rows,
                    "count": len(rows),
                    "truncated": len(rows) >= limit,
                },
                ensure_ascii=False,
                default=str,
            )
        finally:
            engine.dispose()
    except Exception as exc:  # noqa: BLE001
        return f"查询失败：{exc}"
