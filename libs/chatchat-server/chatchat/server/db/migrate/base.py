"""最小化数据库 schema 迁移框架。

设计要点：
- 迁移按单调递增版本注册、按顺序执行，每个版本的 DDL/DML 与版本记录
  处于同一事务，失败即回滚且不记录该版本；
- 版本记录保存在独立的 ``schema_migrations`` 表中（框架基础设施，
  幂等创建）；
- 核心函数接受显式 engine/connection，便于对临时数据库做离线测试；
- 导入本模块不产生任何数据库修改。
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from typing import Callable, List, Optional

from sqlalchemy import Connection, inspect, text

#: 独立的 schema 版本记录表
VERSION_TABLE = "schema_migrations"

_CREATE_VERSION_TABLE = text(
    f"""
    CREATE TABLE IF NOT EXISTS {VERSION_TABLE} (
        version INTEGER PRIMARY KEY,
        name VARCHAR(255) NOT NULL,
        applied_at TIMESTAMP NOT NULL
    )
    """
)


class MigrationError(Exception):
    """迁移流程中可预期的错误（版本回退、失败版本等）。"""


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    upgrade: Callable[[Connection], None]


class MigrationRegistry:
    """按单调递增版本注册迁移，拒绝重复版本与版本空洞。"""

    def __init__(self) -> None:
        self._migrations: List[Migration] = []

    def register(
        self,
        version: int,
        name: str,
        upgrade: Callable[[Connection], None],
    ) -> None:
        if version <= 0:
            raise MigrationError(f"迁移版本必须为正整数，收到 {version}")
        if self._migrations and version == self._migrations[-1].version:
            raise MigrationError(f"迁移版本 {version} 已注册")
        expected = self.latest_version + 1
        if version != expected:
            raise MigrationError(
                f"迁移版本必须连续递增：期望 {expected}，实际为 {version}"
            )
        self._migrations.append(Migration(version=version, name=name, upgrade=upgrade))

    @property
    def migrations(self) -> List[Migration]:
        return list(self._migrations)

    @property
    def latest_version(self) -> int:
        return self._migrations[-1].version if self._migrations else 0


def ensure_version_table(conn: Connection) -> None:
    """幂等创建版本记录表（框架基础设施，非业务迁移内容）。"""
    conn.execute(_CREATE_VERSION_TABLE)


def current_version(conn: Connection) -> Optional[int]:
    """只读查询当前数据库版本；版本表不存在或为空时返回 None。"""
    if not inspect(conn).has_table(VERSION_TABLE):
        return None
    versions = list(
        conn.execute(
            text(f"SELECT version FROM {VERSION_TABLE} ORDER BY version")
        ).scalars()
    )
    if not versions:
        return None
    expected = list(range(1, versions[-1] + 1))
    if versions != expected:
        raise MigrationError(
            f"数据库迁移记录不连续：期望 {expected}，实际为 {versions}。"
            "请先恢复或修复迁移记录。"
        )
    return versions[-1]


def _pending_from_version(
    registry: MigrationRegistry, db_version: Optional[int]
) -> List[Migration]:
    if db_version is None:
        return list(registry.migrations)
    if db_version > registry.latest_version:
        raise MigrationError(
            f"数据库版本 {db_version} 高于代码中最新版本 {registry.latest_version}，"
            "拒绝执行（禁止降级）。请检查代码版本或回退数据库。"
        )
    return [m for m in registry.migrations if m.version > db_version]


def pending_migrations(
    registry: MigrationRegistry,
    conn: Connection,
) -> List[Migration]:
    """计算尚未执行的迁移，按版本升序。"""
    return _pending_from_version(registry, current_version(conn))


@dataclass
class UpgradeResult:
    applied: List[Migration]
    final_version: Optional[int]


def apply_migrations(
    registry: MigrationRegistry,
    conn: Connection,
    before_upgrade: Optional[Callable[[], None]] = None,
) -> UpgradeResult:
    """按顺序执行全部待执行迁移。

    每个迁移与其版本记录处于同一事务：升级体抛异常时回滚本版本的全部
    变更（含业务 DDL/DML）且不写入版本记录，并立即停止后续迁移。

    ``before_upgrade``（可选）在任何迁移执行前调用一次，可用于
    升级前备份等必须在写库之前完成的操作；它抛出的异常会中止整个升级。

    连接传入时应处于无活动事务的状态；本函数内部为每个迁移开启独立
    事务，若检测到只读 autobegin 残留会先回滚清除。
    """
    db_version = current_version(conn)
    pending = _pending_from_version(registry, db_version)
    result = UpgradeResult(applied=[], final_version=db_version)
    if pending and before_upgrade is not None:
        before_upgrade()
    for migration in pending:
        # 清除可能存在的只读 autobegin 残留事务，保证本迁移独立成事务
        if conn.in_transaction():
            conn.rollback()
        with conn.begin():
            # pysqlite 在首条 DML 前不会主动发送 BEGIN；若迁移以 DDL
            # 开始，必须显式开启事务才能让建表等结构变更随异常回滚。
            if conn.dialect.name == "sqlite":
                conn.exec_driver_sql("BEGIN")
            ensure_version_table(conn)
            migration.upgrade(conn)
            conn.execute(
                text(
                    f"INSERT INTO {VERSION_TABLE} (version, name, applied_at) "
                    "VALUES (:version, :name, :applied_at)"
                ),
                {
                    "version": migration.version,
                    "name": migration.name,
                    "applied_at": _dt.datetime.now(_dt.timezone.utc),
                },
            )
        result.applied.append(migration)
        result.final_version = migration.version
    return result


__all__ = [
    "Migration",
    "MigrationError",
    "MigrationRegistry",
    "UpgradeResult",
    "VERSION_TABLE",
    "apply_migrations",
    "current_version",
    "ensure_version_table",
    "pending_migrations",
]
