"""首个管理员初始化 CLI（``chatchat users init-admin``）。

- 密码通过 Click 隐藏输入并二次确认，禁止 password 命令行选项；
- 数据库未显式执行 ``chatchat migrate upgrade`` 时给出可操作提示，
  不自动迁移；
- 已存在 admin 时拒绝再次执行；
- 成功输出仅含 username/id 等非敏感信息；
- 导入本模块不连接或修改数据库。
"""
from __future__ import annotations

import os

import click
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from chatchat.server.db.migrate.base import MigrationError, current_version
from chatchat.server.db.migrate.backup import sqlite_db_file
from chatchat.settings import Settings


def _engine() -> Engine:
    return create_engine(Settings.basic_settings.SQLALCHEMY_DATABASE_URI)


def _has_user_table(engine: Engine) -> bool:
    """只读检查 user_account 是否已迁移（不写库、不建库）。"""
    db_file = sqlite_db_file(engine)
    if db_file is not None and not os.path.isfile(db_file):
        return False
    with engine.connect() as conn:
        db_version = current_version(conn)
        return (
            db_version is not None
            and db_version >= 2
            and inspect(conn).has_table("user_account")
        )


def _do_init(
    engine: Engine,
    username: str,
    display_name: str,
    password: str,
) -> None:
    from chatchat.server.auth import service

    Session = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
        expire_on_commit=False,
    )
    with Session.begin() as session:
        user = service.init_first_admin(session, username, display_name, password)
        username_out, user_id = user.username, user.id
    click.echo(f"管理员创建成功：username={username_out} id={user_id}")


@click.group("users", help="用户管理命令")
def users():
    ...


@users.command(
    "init-admin",
    help="初始化首个管理员（仅当不存在 admin 时）",
)
def init_admin():
    from chatchat.server.auth import service

    engine = _engine()
    try:
        if not _has_user_table(engine):
            raise click.ClickException(
                "尚未检测到 user_account 表。请先执行 "
                "`chatchat migrate upgrade`。"
            )

        username = click.prompt("管理员 username", type=str).strip().lower()
        display_name = click.prompt("管理员显示名称", type=str).strip()
        password = click.prompt(
            "管理员密码",
            type=str,
            hide_input=True,
            confirmation_prompt=True,
        )
        _do_init(engine, username, display_name, password)
    except service.NoAdminLeft as exc:
        raise click.ClickException(
            "系统已存在管理员，无法再次初始化"
        ) from exc
    except service.UsernameConflict as exc:
        raise click.ClickException("username 已存在") from exc
    except service.InvalidInput as exc:
        raise click.ClickException(str(exc)) from exc
    except MigrationError as exc:
        raise click.ClickException(
            f"无法确认数据库迁移状态：{exc}"
        ) from exc
    finally:
        engine.dispose()


__all__ = ["users"]
