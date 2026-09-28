"""内置迁移注册。

当前版本内容（任务 001）只包含 v1 基线迁移：建立 schema 版本记录表。
用户表、conversation owner 等后续业务 schema 变化由新的迁移任务追加
新版本的迁移函数，不修改已发布版本。
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


_MIGRATIONS = [
    (1, "baseline", _v1_baseline),
]


def build_registry() -> MigrationRegistry:
    """构建内置迁移注册表（每次调用返回独立实例）。"""
    registry = MigrationRegistry()
    for version, name, upgrade in _MIGRATIONS:
        registry.register(version, name, upgrade)
    return registry


__all__ = ["build_registry"]
