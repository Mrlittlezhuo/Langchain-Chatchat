"""schema 迁移 CLI（注册为 ``chatchat migrate`` 子命令组）。

- ``chatchat migrate status``：查看当前数据库版本、代码最新版本与待执行迁移；
- ``chatchat migrate upgrade``：显式升级到代码最新版本。

CLI 只显式建库/改 schema 版本，绝不删除表、重建知识库或向量索引。
导入本模块不产生任何数据库修改。
"""
from __future__ import annotations

import os
import sys

from click import group
from sqlalchemy import create_engine

from chatchat.server.db.migrate.base import (
    apply_migrations,
    current_version,
    pending_migrations,
)
from chatchat.server.db.migrate.backup import (
    BackupError,
    backup_sqlite_db,
    sqlite_db_file,
)
from chatchat.server.db.migrate.migrations import build_registry
from chatchat.settings import Settings


def _engine():
    return create_engine(Settings.basic_settings.SQLALCHEMY_DATABASE_URI)


def _fmt_version(version) -> str:
    return "0（无版本记录）" if version is None else str(version)


@group("migrate", help="数据库 schema 版本迁移（仅显式执行）")
def migrate():
    ...


@migrate.command("status", help="查看当前数据库版本、代码最新版本与待执行迁移")
def status_command():
    registry = build_registry()
    engine = _engine()
    try:
        db_file = sqlite_db_file(engine)
        if db_file is not None and not os.path.isfile(db_file):
            db_version = None
            pending = registry.migrations
        else:
            with engine.connect() as conn:
                db_version = current_version(conn)
                pending = pending_migrations(registry, conn)
    except Exception as exc:
        print(f"错误：无法读取迁移状态：{exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        engine.dispose()

    print(f"当前数据库版本：{_fmt_version(db_version)}")
    print(f"代码最新版本：{registry.latest_version}")
    if not pending:
        print("数据库已是最新版本，无需升级。")
        return
    print("待执行迁移：")
    for m in pending:
        print(f"  - v{m.version}: {m.name}")


@migrate.command("upgrade", help="显式升级到代码中最新的 schema 版本")
def upgrade_command():
    registry = build_registry()
    engine = _engine()
    backup_path = None
    try:
        db_file = sqlite_db_file(engine)
        if db_file is not None and not os.path.isfile(db_file):
            print(f"错误：SQLite 数据库文件不存在：{db_file}", file=sys.stderr)
            sys.exit(1)

        def before_upgrade():
            nonlocal backup_path
            if db_file is None:
                print("目标为内存或非 SQLite 数据库，跳过文件备份")
                return
            print(f"目标数据库：{db_file}")
            backup_path = backup_sqlite_db(db_file)
            print(f"升级前备份已创建：{backup_path}")

        with engine.connect() as conn:
            result = apply_migrations(
                registry,
                conn,
                before_upgrade=before_upgrade,
            )
    except BackupError as exc:
        print(f"错误：{exc}（备份失败，升级已中止）", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(
            f"错误：迁移失败：{exc}\n"
            "失败的版本未被记录且其变更已回滚，此前已应用的版本保持生效，"
            "原数据库与备份均已保留。",
            file=sys.stderr,
        )
        sys.exit(1)
    finally:
        engine.dispose()

    if result.applied:
        print("已执行迁移：")
        for m in result.applied:
            print(f"  - v{m.version}: {m.name}")
    else:
        print("无待执行迁移。")
    print(f"最终版本：{_fmt_version(result.final_version)}")
    if backup_path is not None:
        print(f"备份位置：{backup_path}")


__all__ = ["migrate"]
