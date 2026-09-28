"""数据库 schema 迁移包（最小框架 + 内置迁移）。

本包导入时不产生任何数据库修改；所有副作用由显式调用触发。
"""
from chatchat.server.db.migrate.base import (
    Migration,
    MigrationError,
    MigrationRegistry,
    UpgradeResult,
    VERSION_TABLE,
    apply_migrations,
    current_version,
    ensure_version_table,
    pending_migrations,
)
from chatchat.server.db.migrate.backup import (
    BackupError,
    backup_sqlite_db,
    sqlite_db_file,
)
from chatchat.server.db.migrate.migrations import build_registry

__all__ = [
    "BackupError",
    "Migration",
    "MigrationError",
    "MigrationRegistry",
    "UpgradeResult",
    "VERSION_TABLE",
    "apply_migrations",
    "backup_sqlite_db",
    "build_registry",
    "current_version",
    "ensure_version_table",
    "pending_migrations",
    "sqlite_db_file",
]
