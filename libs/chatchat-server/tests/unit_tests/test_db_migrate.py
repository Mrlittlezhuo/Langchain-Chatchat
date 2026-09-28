"""数据库 schema 迁移框架的离线单元测试（任务 001）。

全部测试使用临时目录中的临时 SQLite 数据库或内存数据库，不连接
模型服务、外部网络或真实用户数据库。
"""
import datetime
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest
from click.testing import CliRunner
from sqlalchemy import create_engine, inspect, text

from chatchat.server.db.base import Base
from chatchat.server.db.migrate.base import (
    MigrationError,
    MigrationRegistry,
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
from chatchat.server.db.models.conversation_model import ConversationModel
from chatchat.server.db.models.message_model import MessageModel


# ---------------------------------------------------------------------------
# fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def temp_db_file(tmp_path):
    """临时目录中的空 SQLite 文件型数据库路径。"""
    path = tmp_path / "info.db"
    path.touch()
    return path


def _file_engine(path):
    return create_engine(f"sqlite:///{path}")


def _test_registry() -> MigrationRegistry:
    """测试用注册表：v1 建表，v2 业务 DML，v3 业务 DML。"""
    registry = MigrationRegistry()

    def v1(conn):
        conn.execute(
            text(
                "CREATE TABLE test_items (id INTEGER PRIMARY KEY, "
                "value TEXT NOT NULL)"
            )
        )

    def v2(conn):
        conn.execute(text("INSERT INTO test_items (value) VALUES ('v2')"))

    def v3(conn):
        conn.execute(text("INSERT INTO test_items (value) VALUES ('v3')"))

    registry.register(1, "test-v1", v1)
    registry.register(2, "test-v2", v2)
    registry.register(3, "test-v3", v3)
    return registry


def _failing_registry(fail_version: int) -> MigrationRegistry:
    """v1 正常，``fail_version`` 版本抛异常，v3 在其后。"""
    registry = MigrationRegistry()

    def v1(conn):
        conn.execute(
            text(
                "CREATE TABLE failing_items (id INTEGER PRIMARY KEY, "
                "value TEXT NOT NULL)"
            )
        )

    def v2(conn):
        conn.execute(text("INSERT INTO failing_items (value) VALUES ('partial')"))
        raise RuntimeError("simulated migration failure")

    def v3(conn):
        conn.execute(text("INSERT INTO failing_items (value) VALUES ('never')"))

    registry.register(1, "ok", v1)
    registry.register(2, "fail", v2)
    registry.register(3, "after-fail", v3)
    assert fail_version == 2
    return registry


# ---------------------------------------------------------------------------
# 版本注册与顺序
# ---------------------------------------------------------------------------


def test_builtin_registry_order_and_latest():
    registry = build_registry()
    assert [m.version for m in registry.migrations] == [1]
    assert registry.latest_version == 1


def test_registry_rejects_duplicate_version():
    registry = MigrationRegistry()
    registry.register(1, "a", lambda conn: None)
    with pytest.raises(MigrationError):
        registry.register(1, "b", lambda conn: None)


def test_registry_rejects_gap():
    registry = MigrationRegistry()
    registry.register(1, "a", lambda conn: None)
    with pytest.raises(MigrationError):
        registry.register(3, "c", lambda conn: None)
    assert [m.version for m in registry.migrations] == [1]


def test_registry_must_start_at_one():
    registry = MigrationRegistry()
    with pytest.raises(MigrationError):
        registry.register(2, "b", lambda conn: None)
    assert registry.migrations == []


def test_registry_rejects_non_positive_version():
    registry = MigrationRegistry()
    with pytest.raises(MigrationError):
        registry.register(0, "zero", lambda conn: None)


# ---------------------------------------------------------------------------
# 首次升级 / 幂等 / 顺序
# ---------------------------------------------------------------------------


def test_first_upgrade_on_empty_file_db(temp_db_file):
    registry = build_registry()
    engine = _file_engine(temp_db_file)
    with engine.connect() as conn:
        assert current_version(conn) is None
        result = apply_migrations(registry, conn)
        assert [m.version for m in result.applied] == [1]
        assert result.final_version == 1
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT version, name FROM schema_migrations")
        ).fetchall()
        assert [(r[0], r[1]) for r in rows] == [(1, "baseline")]
    engine.dispose()


def test_current_version_does_not_create_version_table(temp_db_file):
    engine = _file_engine(temp_db_file)
    with engine.connect() as conn:
        assert current_version(conn) is None
        assert not inspect(conn).has_table("schema_migrations")
    engine.dispose()


def test_double_upgrade_is_idempotent(temp_db_file):
    registry = build_registry()
    engine = _file_engine(temp_db_file)
    with engine.connect() as conn:
        first = apply_migrations(registry, conn)
        assert [m.version for m in first.applied] == [1]
        second = apply_migrations(registry, conn)
        assert second.applied == []
        assert second.final_version == 1
    with engine.connect() as conn:
        assert conn.execute(
            text("SELECT COUNT(*) FROM schema_migrations")
        ).scalar() == 1
    engine.dispose()


def test_no_pending_migration_does_not_run_before_upgrade(temp_db_file):
    registry = build_registry()
    engine = _file_engine(temp_db_file)
    callbacks = []
    with engine.connect() as conn:
        apply_migrations(registry, conn)
        result = apply_migrations(
            registry,
            conn,
            before_upgrade=lambda: callbacks.append("called"),
        )
    assert result.applied == []
    assert callbacks == []
    engine.dispose()


def test_in_memory_db_upgrades_without_backup(tmp_path):
    """内存数据库可以正常升级（不要求文件备份）。"""
    registry = build_registry()
    engine = create_engine("sqlite:///:memory:")
    assert sqlite_db_file(engine) is None
    with engine.connect() as conn:
        result = apply_migrations(registry, conn)
        assert result.final_version == 1
        assert current_version(conn) == 1
    engine.dispose()


def test_multiple_versions_run_in_order(temp_db_file):
    registry = _test_registry()
    engine = _file_engine(temp_db_file)
    with engine.connect() as conn:
        result = apply_migrations(registry, conn)
        assert [m.version for m in result.applied] == [1, 2, 3]
        assert result.final_version == 3
        values = [
            r[0]
            for r in conn.execute(text("SELECT value FROM test_items ORDER BY id"))
        ]
        assert values == ["v2", "v3"]
    engine.dispose()


def test_pending_migrations_computed_from_db_version(temp_db_file):
    registry = _test_registry()
    engine = _file_engine(temp_db_file)
    with engine.connect() as conn:
        apply_migrations(registry, conn)
        # 截断版本记录到 v1，模拟只执行到 v1 的旧库
        conn.execute(text("DELETE FROM schema_migrations WHERE version > 1"))
        conn.commit()
    with engine.connect() as conn:
        pending = pending_migrations(registry, conn)
        assert [m.version for m in pending] == [2, 3]
    engine.dispose()


# ---------------------------------------------------------------------------
# 失败回滚
# ---------------------------------------------------------------------------


def test_failed_version_is_not_recorded_and_rolls_back(temp_db_file):
    registry = _failing_registry(2)
    engine = _file_engine(temp_db_file)
    with pytest.raises(RuntimeError, match="simulated migration failure"):
        with engine.connect() as conn:
            apply_migrations(registry, conn)
    with engine.connect() as conn:
        assert current_version(conn) == 1
        assert conn.execute(text("SELECT COUNT(*) FROM failing_items")).scalar() == 0
        versions = [
            r[0] for r in conn.execute(text("SELECT version FROM schema_migrations"))
        ]
        assert versions == [1]
    engine.dispose()


def test_failed_migration_stops_later_versions(temp_db_file):
    registry = _failing_registry(2)
    engine = _file_engine(temp_db_file)
    with pytest.raises(RuntimeError):
        with engine.connect() as conn:
            apply_migrations(registry, conn)
    with engine.connect() as conn:
        assert current_version(conn) == 1
    engine.dispose()


def test_failed_first_migration_rolls_back_sqlite_ddl(temp_db_file):
    registry = MigrationRegistry()

    def failing_ddl(conn):
        conn.execute(text("CREATE TABLE should_rollback (id INTEGER)"))
        raise RuntimeError("simulated DDL failure")

    registry.register(1, "failing-ddl", failing_ddl)
    engine = _file_engine(temp_db_file)
    with pytest.raises(RuntimeError, match="simulated DDL failure"):
        with engine.connect() as conn:
            apply_migrations(registry, conn)
    with engine.connect() as conn:
        assert not inspect(conn).has_table("should_rollback")
        assert not inspect(conn).has_table("schema_migrations")
    engine.dispose()


# ---------------------------------------------------------------------------
# 版本回退拒绝
# ---------------------------------------------------------------------------


def test_downgrade_refused(temp_db_file):
    registry = _test_registry()
    engine = _file_engine(temp_db_file)
    with engine.connect() as conn:
        apply_migrations(registry, conn)
    smaller = MigrationRegistry()
    smaller.register(1, "only-v1", lambda conn: None)
    with engine.connect() as conn:
        with pytest.raises(MigrationError):
            pending_migrations(smaller, conn)
        with pytest.raises(MigrationError):
            apply_migrations(smaller, conn)
    engine.dispose()


def test_non_contiguous_database_history_is_rejected(temp_db_file):
    registry = _test_registry()
    engine = _file_engine(temp_db_file)
    with engine.connect() as conn:
        apply_migrations(registry, conn)
        conn.execute(text("DELETE FROM schema_migrations WHERE version = 2"))
        conn.commit()
        with pytest.raises(MigrationError, match="不连续"):
            current_version(conn)
    engine.dispose()


# ---------------------------------------------------------------------------
# SQLite 备份
# ---------------------------------------------------------------------------


def test_sqlite_db_file_detection(temp_db_file):
    assert sqlite_db_file(_file_engine(temp_db_file)) == str(temp_db_file)
    # 用字符串 URL 判断，避免在非 SQLite 驱动环境下加载方言
    assert sqlite_db_file("sqlite:///:memory:") is None
    assert sqlite_db_file("sqlite:///file::memory:") is None
    assert sqlite_db_file("sqlite:///file:tmp") is None
    assert sqlite_db_file("postgresql://u:p@localhost/db") is None
    assert sqlite_db_file(f"sqlite:///{temp_db_file}") == str(temp_db_file)
    for engine in (
        _file_engine(temp_db_file),
        create_engine("sqlite:///:memory:"),
    ):
        engine.dispose()


def test_backup_created_before_upgrade_and_readable(temp_db_file):
    registry = _test_registry()
    engine = _file_engine(temp_db_file)
    # 模拟升级前已存在的业务数据
    with engine.connect() as conn:
        conn.execute(
            text("CREATE TABLE pre_existing (id INTEGER PRIMARY KEY, value TEXT)")
        )
        conn.execute(text("INSERT INTO pre_existing (value) VALUES ('old-data')"))
        conn.commit()

    backups = []

    def before_upgrade():
        path = backup_sqlite_db(str(temp_db_file))
        backups.append(path)
        assert Path(path).is_file()

    with engine.connect() as conn:
        apply_migrations(registry, conn, before_upgrade=before_upgrade)
    # 每次升级只备份一次（本次共 3 个迁移）
    assert len(backups) == 1
    # 备份内容可读，且是升级前快照：含预置数据，不含 v1 才创建的 test_items
    conn = sqlite3.connect(backups[0])
    try:
        rows = [r for r in conn.execute("SELECT value FROM pre_existing")]
        assert [r[0] for r in rows] == ["old-data"]
        tables = [
            r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        ]
        assert "pre_existing" in tables
        assert "test_items" not in tables
    finally:
        conn.close()
    engine.dispose()


def test_backup_not_overwritten(temp_db_file):
    first = backup_sqlite_db(str(temp_db_file))
    second = backup_sqlite_db(str(temp_db_file))
    assert first != second
    assert Path(first).is_file() and Path(second).is_file()


def test_backup_name_collision_never_overwrites(
    temp_db_file, monkeypatch
):
    from chatchat.server.db.migrate import backup as backup_module

    class FixedDateTime(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2024, 1, 2, 3, 4, 5, tzinfo=tz)

    fake_datetime_module = SimpleNamespace(
        datetime=FixedDateTime,
        timezone=datetime.timezone,
    )
    fake_uuid = SimpleNamespace(hex="deadbeef" * 4)
    monkeypatch.setattr(backup_module, "_dt", fake_datetime_module)
    monkeypatch.setattr(backup_module.uuid, "uuid4", lambda: fake_uuid)

    collision = Path(f"{temp_db_file}.bak-20240102T030405-deadbeef.db")
    collision.write_bytes(b"keep-existing-backup")
    with pytest.raises(BackupError, match="唯一"):
        backup_sqlite_db(str(temp_db_file))
    assert collision.read_bytes() == b"keep-existing-backup"


def test_backup_includes_committed_wal_content(tmp_path):
    db_path = tmp_path / "wal.db"
    source = sqlite3.connect(str(db_path))
    try:
        source.execute("PRAGMA journal_mode=WAL")
        source.execute("PRAGMA wal_autocheckpoint=0")
        source.execute("CREATE TABLE items (value TEXT)")
        source.commit()
        source.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        source.execute("INSERT INTO items VALUES ('committed-in-wal')")
        source.commit()

        backup_path = backup_sqlite_db(str(db_path))
        with sqlite3.connect(backup_path) as backup:
            assert backup.execute("SELECT value FROM items").fetchall() == [
                ("committed-in-wal",)
            ]
    finally:
        source.close()


def test_backup_missing_source_raises(temp_db_file):
    missing = temp_db_file.parent / "nope.db"
    with pytest.raises(BackupError):
        backup_sqlite_db(str(missing))


# ---------------------------------------------------------------------------
# 数据保留
# ---------------------------------------------------------------------------


def _seed_conversations(session_factory, conv_ids):
    with session_factory() as session:
        for conv_id in conv_ids:
            session.add(
                ConversationModel(
                    id=conv_id, name=f"对话 {conv_id}", chat_type="local"
                )
            )
            session.add(MessageModel(id=conv_id + "-m", conversation_id=conv_id))
        session.commit()


def test_sample_data_preserved_through_noop_migrations(tmp_path):
    """空操作迁移（无 DDL）前后 conversation/message 数据数量与值一致。"""
    db_path = tmp_path / "preserved.db"
    Base.metadata.create_all(bind=create_engine(f"sqlite:///{db_path}"))

    from sqlalchemy.orm import sessionmaker

    engine = _file_engine(db_path)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    conv_ids = ["conv-a", "conv-b"]
    _seed_conversations(SessionLocal, conv_ids)

    def noop(conn):
        pass

    registry = MigrationRegistry()
    registry.register(1, "noop-a", noop)
    registry.register(2, "noop-b", noop)

    with engine.connect() as conn:
        result = apply_migrations(registry, conn)
        assert result.final_version == 2

    with SessionLocal() as session:
        convs = session.query(ConversationModel).order_by(ConversationModel.id).all()
        msgs = session.query(MessageModel).order_by(MessageModel.id).all()
        assert [c.id for c in convs] == conv_ids
        assert [c.name for c in convs] == [f"对话 {c}" for c in conv_ids]
        assert [m.id for m in msgs] == [c + "-m" for c in conv_ids]
        assert len(convs) == 2 and len(msgs) == 2
    engine.dispose()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cli(monkeypatch, tmp_path, *args):
    """运行 chatchat migrate CLI 子命令，指向临时数据库。"""
    from chatchat import settings as settings_module
    from chatchat.server.db.migrate import cli as migrate_cli

    db_path = tmp_path / "cli.db"
    db_path.touch()
    uri = f"sqlite:///{db_path}"
    monkeypatch.setattr(settings_module.Settings.basic_settings, "SQLALCHEMY_DATABASE_URI", uri)
    monkeypatch.setenv("CHATCHAT_ROOT", str(tmp_path))
    runner = CliRunner()
    return runner.invoke(migrate_cli.migrate, list(args)), db_path


def test_cli_status_shows_pending_and_final(tmp_path, monkeypatch):
    runner_result, db_path = _cli(monkeypatch, tmp_path, "status")
    assert runner_result.exit_code == 0
    assert "当前数据库版本" in runner_result.output
    assert "代码最新版本：1" in runner_result.output
    assert "v1" in runner_result.output
    with sqlite3.connect(str(db_path)) as conn:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    assert ("schema_migrations",) not in tables

    upgrade_result, _ = _cli(monkeypatch, tmp_path, "upgrade")
    assert upgrade_result.exit_code == 0
    assert "已执行迁移" in upgrade_result.output
    assert "最终版本：1" in upgrade_result.output
    assert "备份" in upgrade_result.output

    status_result, _ = _cli(monkeypatch, tmp_path, "status")
    assert status_result.exit_code == 0
    assert "已是最新版本" in status_result.output


def test_cli_status_does_not_create_missing_database(tmp_path, monkeypatch):
    from chatchat import settings as settings_module
    from chatchat.server.db.migrate import cli as migrate_cli

    db_path = tmp_path / "missing.db"
    monkeypatch.setattr(
        settings_module.Settings.basic_settings,
        "SQLALCHEMY_DATABASE_URI",
        f"sqlite:///{db_path}",
    )
    monkeypatch.setenv("CHATCHAT_ROOT", str(tmp_path))
    result = CliRunner().invoke(migrate_cli.migrate, ["status"])
    assert result.exit_code == 0
    assert "v1" in result.output
    assert not db_path.exists()


def test_cli_upgrade_is_idempotent(tmp_path, monkeypatch):
    _, db_path = _cli(monkeypatch, tmp_path, "upgrade")
    result, _ = _cli(monkeypatch, tmp_path, "upgrade")
    assert result.exit_code == 0
    assert "无待执行迁移" in result.output
    assert "最终版本：1" in result.output
    assert Path(db_path).is_file()
    backups = [p for p in db_path.parent.iterdir() if ".bak-" in p.name]
    assert len(backups) == 1


def test_cli_upgrade_creates_backup_file(tmp_path, monkeypatch):
    result, db_path = _cli(monkeypatch, tmp_path, "upgrade")
    assert result.exit_code == 0
    backups = [p for p in Path(db_path.parent).iterdir() if ".bak-" in p.name]
    assert len(backups) == 1
    assert str(backups[0]) in result.output


def test_cli_upgrade_failure_exit_code(tmp_path, monkeypatch):
    from chatchat.server.db.migrate import cli as migrate_cli

    def fail_migration(*args, **kwargs):
        raise RuntimeError("simulated CLI migration failure")

    monkeypatch.setattr(migrate_cli, "apply_migrations", fail_migration)
    result, _ = _cli(monkeypatch, tmp_path, "upgrade")
    assert result.exit_code != 0
    assert "迁移失败" in result.output
    assert "simulated CLI migration failure" in result.output


def test_cli_backup_failure_stops_upgrade(tmp_path, monkeypatch):
    from chatchat.server.db.migrate import cli as migrate_cli

    def fail_backup(*args, **kwargs):
        raise BackupError("simulated backup failure")

    monkeypatch.setattr(migrate_cli, "backup_sqlite_db", fail_backup)
    result, db_path = _cli(monkeypatch, tmp_path, "upgrade")
    assert result.exit_code != 0
    assert "备份失败，升级已中止" in result.output
    with sqlite3.connect(str(db_path)) as conn:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    assert ("schema_migrations",) not in tables


def test_cli_import_does_not_touch_database(tmp_path, monkeypatch):
    """导入 CLI 模块不产生任何数据库修改。"""
    from chatchat import settings as settings_module

    db_path = tmp_path / "fresh.db"
    uri = f"sqlite:///{db_path}"
    monkeypatch.setattr(
        settings_module.Settings.basic_settings,
        "SQLALCHEMY_DATABASE_URI",
        uri,
    )
    monkeypatch.setenv("CHATCHAT_ROOT", str(tmp_path))
    # 重新导入（已缓存则为 no-op），确认导入过程不创建/修改数据库文件
    import importlib
    import chatchat.server.db.migrate.cli as cli_mod

    importlib.reload(cli_mod)
    with sqlite3.connect(str(db_path)) as conn:
        tables = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        ]
    assert "schema_migrations" not in tables


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-q"]))
