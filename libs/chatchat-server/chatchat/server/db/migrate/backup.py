"""SQLite 升级前备份。

- 仅对 sqlite:// 文件型数据库生效；内存库、临时文件（file::memory:、
  file:tmp、file:data 等 SQLite 临时文件前缀）以及非 SQLite 数据库
  不需要文件备份；
- 备份文件位于源库同目录，名为 ``{源库名}.bak-{UTC时间戳}-{8位hex}.db``，
  时间戳保证文件名唯一，已存在的同名备份绝不覆盖；
- 使用 SQLite online backup API 获得包含 WAL 已提交内容的一致快照；
- 备份在升级前执行，备份失败时不得继续迁移（由调用方保证中止）。
"""
from __future__ import annotations

import datetime as _dt
import os
import sqlite3
import uuid
from contextlib import closing
from pathlib import Path
from typing import Optional, Union

from sqlalchemy.engine import URL, Engine, make_url


class BackupError(Exception):
    """备份失败（读取源库或写入备份文件出错）。"""


def sqlite_db_file(engine_or_url: Union[Engine, URL, str]) -> Optional[str]:
    """若指向 SQLite 文件型数据库，返回其文件绝对路径；否则返回 None。

    接受 Engine、URL 或 URL 字符串；传入字符串时不加载数据库方言，
    便于在非 SQLite 环境下做判断。
    """
    if isinstance(engine_or_url, Engine):
        url = engine_or_url.url
    elif isinstance(engine_or_url, str):
        url = make_url(engine_or_url)
    else:
        url = engine_or_url
    if url.get_backend_name() != "sqlite":
        return None
    database = url.database
    if not database or database == ":memory:":
        return None
    if database.startswith("file:"):
        # SQLite 临时文件前缀（file:tmp、file:data、file:memory: 等）不是真实文件
        return None
    return os.path.abspath(database)


def _backup_is_readable(path: str) -> bool:
    """校验备份是合法且可读的 SQLite 数据库。"""
    try:
        uri = f"{Path(path).resolve().as_uri()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        try:
            rows = conn.execute("PRAGMA integrity_check").fetchall()
        finally:
            conn.close()
    except (OSError, sqlite3.Error):
        return False
    return rows == [("ok",)]


def _reserve_backup_path(db_file: str, stamp: str) -> str:
    """原子占用一个新备份路径，绝不覆盖并发或既有文件。"""
    for _ in range(32):
        candidate = f"{db_file}.bak-{stamp}-{uuid.uuid4().hex[:8]}.db"
        try:
            fd = os.open(
                candidate,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o600,
            )
        except FileExistsError:
            continue
        except OSError as exc:
            raise BackupError(f"无法创建备份文件：{candidate}：{exc}") from exc
        os.close(fd)
        return candidate
    raise BackupError("无法生成唯一的 SQLite 备份文件名，请稍后重试")


def backup_sqlite_db(db_file: str) -> str:
    """在源库同目录创建带时间戳的唯一备份，返回备份文件路径。

    备份成功后会做一次完整性校验；校验或复制失败时不留下损坏的备份文件
    并抛出 ``BackupError``。已存在的同名备份绝不覆盖。
    """
    if not os.path.isfile(db_file):
        raise BackupError(f"待备份的 SQLite 文件不存在：{db_file}")
    stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%S")
    backup_path = _reserve_backup_path(db_file, stamp)
    try:
        source_uri = f"{Path(db_file).resolve().as_uri()}?mode=ro"
        with closing(sqlite3.connect(source_uri, uri=True)) as source:
            with closing(sqlite3.connect(backup_path)) as destination:
                source.backup(destination)
        if not _backup_is_readable(backup_path):
            raise BackupError(f"备份文件校验失败：{backup_path}")
    except Exception as exc:
        if os.path.exists(backup_path):
            try:
                os.remove(backup_path)
            except OSError:
                pass
        raise BackupError(f"创建 SQLite 备份失败：{exc}") from exc
    return backup_path


__all__ = ["BackupError", "backup_sqlite_db", "sqlite_db_file"]
