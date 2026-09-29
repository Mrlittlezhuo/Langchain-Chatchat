"""内置迁移注册。

- v1（任务 001）：建立 schema 版本记录表。
- v2（任务 002）：新增最小用户账户表 ``user_account``，不创建默认账户，
  不修改 conversation/message 与知识库表。
- v3（任务 003）：conversation 增加 ``owner_id``、``update_time`` 与
  ``(owner_id, update_time)`` 联合索引；旧行 ``owner_id`` 保持 NULL（由
  后续存量迁移任务归属），``update_time`` 回填为 ``create_time``。

已发布版本不得修改；后续业务 schema 变化追加新版本迁移函数。
"""
from __future__ import annotations

from sqlalchemy import Connection, text

from chatchat.server.db.migrate.base import (
    Migration,
    MigrationRegistry,
    VERSION_TABLE,
)


def _v1_baseline(conn: Connection) -> None:
    """v1：建立 schema 版本记录表（迁移框架基线）。"""
    conn.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS {VERSION_TABLE} (
                version INTEGER PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                applied_at TIMESTAMP NOT NULL
            )
            """
        )
    )


_USER_ACCOUNT_TABLE = """
CREATE TABLE user_account (
    id VARCHAR(32) PRIMARY KEY,
    username VARCHAR(64) NOT NULL,
    display_name VARCHAR(100) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(16) NOT NULL DEFAULT 'user',
    status VARCHAR(16) NOT NULL DEFAULT 'active',
    must_change_password BOOLEAN NOT NULL DEFAULT TRUE,
    auth_version INTEGER NOT NULL DEFAULT 1,
    create_time TIMESTAMP NOT NULL,
    update_time TIMESTAMP NOT NULL,
    CHECK (role IN ('admin', 'user')),
    CHECK (status IN ('active', 'disabled')),
    CHECK (auth_version >= 1)
)
"""

_USER_ACCOUNT_INDEXES = [
    "CREATE UNIQUE INDEX ix_user_account_username ON user_account (username)",
    "CREATE INDEX ix_user_account_role ON user_account (role)",
    "CREATE INDEX ix_user_account_status ON user_account (status)",
]


def _v2_user_account(conn: Connection) -> None:
    """v2：新增最小用户账户表（仅 schema，不创建默认账户）。"""
    conn.execute(text(_USER_ACCOUNT_TABLE))
    for stmt in _USER_ACCOUNT_INDEXES:
        conn.execute(text(stmt))


def _v3_conversation_owner(conn: Connection) -> None:
    """v3：conversation 增加 owner_id / update_time 与联合索引。

    - 业务表 conversation 由应用启动的 ``create_all`` 创建，独立于版本迁移，
      因此在只跑迁移的"空库"上可能尚不存在；此时直接跳过（后续由
      create_all 用新版模型创建带新字段的表）。
    - 已存在的表：缺少 ``owner_id``/``update_time`` 时分别补充；
      ``update_time`` 仅在新加列时回填为 ``create_time``，无值时用当前时间。
    - 旧行 ``owner_id`` 保持 NULL（存量归属由后续任务处理）。
    - 不修改既有 conversation/message 的行数与内容。
    - 重复执行安全：已存在的列/索引不重复创建。
    """
    from sqlalchemy import inspect

    inspector = inspect(conn)
    if "conversation" not in inspector.get_table_names():
        # 业务表尚未创建；由 create_all 用新版模型创建
        return

    existing_cols = {c["name"] for c in inspector.get_columns("conversation")}
    if "owner_id" not in existing_cols:
        conn.execute(text("ALTER TABLE conversation ADD COLUMN owner_id VARCHAR(32)"))
    if "update_time" not in existing_cols:
        conn.execute(text("ALTER TABLE conversation ADD COLUMN update_time TIMESTAMP"))
        conn.execute(text(
            "UPDATE conversation SET update_time = COALESCE(create_time, CURRENT_TIMESTAMP)"
        ))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_conversation_owner_update_time "
        "ON conversation (owner_id, update_time)"
    ))


_MIGRATIONS = [
    (1, "baseline", _v1_baseline),
    (2, "user_account", _v2_user_account),
    (3, "conversation_owner", _v3_conversation_owner),
]


def build_registry() -> MigrationRegistry:
    """构建内置迁移注册表（每次调用返回独立实例）。"""
    registry = MigrationRegistry()
    for version, name, upgrade in _MIGRATIONS:
        registry.register(version, name, upgrade)
    return registry


__all__ = ["build_registry"]
