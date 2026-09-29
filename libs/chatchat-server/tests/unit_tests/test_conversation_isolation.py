"""会话与消息后端隔离离线测试（任务 003）。

覆盖用户 A/B 的基本隔离行为：

- 新会话自动归属当前用户，客户端不能指定 owner；
- A/B 会话列表互不可见；
- A 读取、重命名、删除 B 的会话均为 404；
- A 不能读取或反馈 B 的消息；
- 删除 A 的会话不影响 B；
- 未登录返回 401，必须改密的用户返回 403；
- 主聊天对其他用户 conversation_id 在模型调用前返回 404（mock 模型）；
- owner 正确时消息创建和回答更新使用同一会话。

测试只使用临时 SQLite，不连接模型、网络或真实数据库；模型相关部分
使用 mock。
"""
import sys
import types

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# ---------------------------------------------------------------------------
# 在导入 chat_routes 之前，先打桩 chatchat.server.chat.kb_chat。
# kb_chat 的导入链（search_local_knowledgebase）在模块加载时会执行一次
# 真实知识库数据库读取（list_kbs），离线测试无法提供该库。主聊天隔离测试
# 只关心 chat_completions 处理器，不依赖 kb_chat 的实现，因此用桩替换。
# ---------------------------------------------------------------------------
_kb_stub = types.ModuleType("chatchat.server.chat.kb_chat")
_kb_stub.kb_chat = lambda *args, **kwargs: None
sys.modules["chatchat.server.chat.kb_chat"] = _kb_stub


from chatchat.server.db import session as db_session
from chatchat.server.db.base import Base
from chatchat.server.db.migrate.base import apply_migrations
from chatchat.server.db.migrate.migrations import build_registry
from chatchat.server.db.models.conversation_model import ConversationModel
from chatchat.server.db.models.message_model import MessageModel
from chatchat.server.db.models.user_model import UserModel  # noqa: F401  (注册到 Base.metadata)
from chatchat.server.db.repository import (
    add_message,
    update_message,
)
from chatchat.server.auth import jwt as auth_jwt
from chatchat.server.auth import service
from chatchat.server.api_server.chat_routes import chat_router
from chatchat.server.api_server.conversation_routes import conversation_router


# ---------------------------------------------------------------------------
# fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def secret(monkeypatch):
    """设置一个 >=32 字节的测试密钥（非真实密钥）。"""
    key = "unit-test-secret-key" + "0" * 20
    monkeypatch.setenv("CHATCHAT_AUTH_SECRET", key)
    return key


@pytest.fixture
def temp_user_db(tmp_path):
    """临时文件库：迁移到 v3 + 业务表（conversation/message）。"""
    path = tmp_path / "conv.db"
    path.touch()
    engine = create_engine(f"sqlite:///{path}")
    with engine.connect() as conn:
        apply_migrations(build_registry(), conn)
    # 业务表由 create_all 用新版模型创建（conversation 含 owner_id/update_time/索引）
    Base.metadata.create_all(engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    yield {"engine": engine, "Session": Session, "path": path}
    engine.dispose()


@pytest.fixture
def client(temp_user_db, secret):
    """FastAPI TestClient：会话路由 + 主聊天路由，get_db 覆盖指向临时库。"""
    app = FastAPI()
    app.include_router(conversation_router)
    app.include_router(chat_router)

    def override_get_db():
        s = temp_user_db["Session"]()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[db_session.get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client


def _mk_user(temp_user_db, username, role="user", must_change_password=False):
    """在临时库创建用户，返回其非敏感字段。"""
    S = temp_user_db["Session"]
    s = S()
    try:
        u = service.create_user(
            s,
            username=username,
            display_name=username.title(),
            password="password1234",
            role=role,
        )
        u.must_change_password = must_change_password
        s.commit()
        return {
            "id": u.id,
            "username": u.username,
            "role": u.role,
            "auth_version": u.auth_version,
        }
    finally:
        s.close()


def _headers(temp_user_db, secret, username):
    u = _mk_user(temp_user_db, username)
    return {"Authorization": f"Bearer {auth_jwt.create_token(u['id'], u['auth_version'])}"}, u


def _create_conv(client, headers, name="t", chat_type="llm_chat"):
    r = client.post("/conversations", headers=headers, json={"name": name, "chat_type": chat_type})
    assert r.status_code == 200, r.text
    return r.json()["id"]


# ---------------------------------------------------------------------------
# 会话创建：自动归属当前用户，客户端不能指定 owner
# ---------------------------------------------------------------------------


def test_new_conversation_owned_by_server_not_client(client, temp_user_db, secret):
    hdr, a = _headers(temp_user_db, secret, "alice")
    # 请求体里尝试指定 owner，应被忽略
    r = client.post(
        "/conversations",
        headers=hdr,
        json={"name": "x", "chat_type": "llm_chat", "owner_id": "attacker"},
    )
    assert r.status_code == 200
    cid = r.json()["id"]
    s = temp_user_db["Session"]()
    try:
        c = s.get(ConversationModel, cid)
        assert c is not None
        assert c.owner_id == a["id"]
        assert "owner_id" not in r.json()  # 响应不返回 owner_id
    finally:
        s.close()


def test_unlogged_create_conversation_401(client):
    r = client.post("/conversations", json={"name": "x", "chat_type": "llm_chat"})
    assert r.status_code == 401


def test_must_change_password_403(client, temp_user_db, secret):
    S = temp_user_db["Session"]
    s = S()
    try:
        u = service.create_user(
            s, username="bob", display_name="Bob", password="password1234", role="user"
        )
        u.must_change_password = True
        s.commit()
        token = auth_jwt.create_token(u.id, u.auth_version)
    finally:
        s.close()
    hdr = {"Authorization": f"Bearer {token}"}
    assert client.post("/conversations", headers=hdr, json={"name": "x"}).status_code == 403
    assert client.get("/conversations", headers=hdr).status_code == 403


# ---------------------------------------------------------------------------
# A/B 列表互不可见
# ---------------------------------------------------------------------------


def test_lists_are_per_user(client, temp_user_db, secret):
    hdr_a, a = _headers(temp_user_db, secret, "alice")
    hdr_b, b = _headers(temp_user_db, secret, "bob")
    ca = _create_conv(client, hdr_a, "only-a")
    cb = _create_conv(client, hdr_b, "only-b")

    a_ids = {c["id"] for c in client.get("/conversations", headers=hdr_a).json()}
    b_ids = {c["id"] for c in client.get("/conversations", headers=hdr_b).json()}
    assert ca in a_ids and cb not in a_ids
    assert cb in b_ids and ca not in b_ids


# ---------------------------------------------------------------------------
# A 读取 / 重命名 / 删除 B 的会话均为 404
# ---------------------------------------------------------------------------


def test_a_cannot_read_rename_delete_b_conversation(client, temp_user_db, secret):
    hdr_a, a = _headers(temp_user_db, secret, "alice")
    hdr_b, b = _headers(temp_user_db, secret, "bob")
    cb = _create_conv(client, hdr_b, "secret")

    assert client.get(f"/conversations/{cb}", headers=hdr_a).status_code == 404
    assert client.patch(f"/conversations/{cb}", headers=hdr_a, json={"name": "hax"}).status_code == 404
    assert client.delete(f"/conversations/{cb}", headers=hdr_a).status_code == 404

    # B 的会话仍在
    assert client.get(f"/conversations/{cb}", headers=hdr_b).status_code == 200


def test_a_cannot_read_messages_of_b_conversation(client, temp_user_db, secret):
    hdr_a, a = _headers(temp_user_db, secret, "alice")
    hdr_b, b = _headers(temp_user_db, secret, "bob")
    cb = _create_conv(client, hdr_b, "secret")
    s = temp_user_db["Session"]()
    try:
        add_message(s, cb, b["id"], "llm_chat", "q", response="a")
    finally:
        s.close()

    assert client.get(f"/conversations/{cb}/messages", headers=hdr_a).status_code == 404
    r = client.get(f"/conversations/{cb}/messages", headers=hdr_b)
    assert r.status_code == 200
    assert [m["query"] for m in r.json()["messages"]] == ["q"]


# ---------------------------------------------------------------------------
# 删除 A 的会话不影响 B
# ---------------------------------------------------------------------------


def test_delete_a_conversation_does_not_affect_b(client, temp_user_db, secret):
    hdr_a, a = _headers(temp_user_db, secret, "alice")
    hdr_b, b = _headers(temp_user_db, secret, "bob")
    ca = _create_conv(client, hdr_a, "a-conv")
    cb = _create_conv(client, hdr_b, "b-conv")
    s = temp_user_db["Session"]()
    try:
        add_message(s, ca, a["id"], "llm_chat", "qa", response="ra")
        add_message(s, cb, b["id"], "llm_chat", "qb", response="rb")
    finally:
        s.close()

    assert client.delete(f"/conversations/{ca}", headers=hdr_a).status_code == 200

    s = temp_user_db["Session"]()
    try:
        assert s.get(ConversationModel, ca) is None
        # A 的消息被同步删除
        assert s.query(MessageModel).filter_by(conversation_id=ca).count() == 0
        # B 的会话与消息不受影响
        assert s.get(ConversationModel, cb) is not None
        assert s.query(MessageModel).filter_by(conversation_id=cb).count() == 1
    finally:
        s.close()


# ---------------------------------------------------------------------------
# 消息反馈不能跨 owner
# ---------------------------------------------------------------------------


def test_a_cannot_feedback_b_message(client, temp_user_db, secret):
    hdr_a, a = _headers(temp_user_db, secret, "alice")
    hdr_b, b = _headers(temp_user_db, secret, "bob")
    cb = _create_conv(client, hdr_b, "secret")
    s = temp_user_db["Session"]()
    try:
        mid = add_message(s, cb, b["id"], "llm_chat", "q", response="a")
    finally:
        s.close()

    # A 反馈 B 的消息 → 404
    assert client.post("/chat/feedback", headers=hdr_a, json={"message_id": mid, "score": 100}).status_code == 404
    # B 反馈自己的消息 → 200
    assert client.post("/chat/feedback", headers=hdr_b, json={"message_id": mid, "score": 100}).status_code == 200


# ---------------------------------------------------------------------------
# 主聊天：其他用户 conversation_id 在模型调用前 404（mock 模型）
# ---------------------------------------------------------------------------


def test_chat_other_user_conversation_id_404_before_model(client, temp_user_db, secret, monkeypatch):
    import chatchat.server.api_server.chat_routes as cr

    model_called = {"n": 0}

    async def fake_chat(*args, **kwargs):
        model_called["n"] += 1
        return {"choices": [{"message": "should-not-reach"}]}

    monkeypatch.setattr(cr, "chat", fake_chat)

    hdr_a, a = _headers(temp_user_db, secret, "alice")
    hdr_b, b = _headers(temp_user_db, secret, "bob")
    cb = _create_conv(client, hdr_b, "secret")

    body = {
        "model": "qwen:7b",
        "stream": False,
        "messages": [{"role": "user", "content": "hi"}],
        "conversation_id": cb,
    }
    r = client.post("/chat/chat/completions", headers=hdr_a, json=body)
    assert r.status_code == 404
    assert model_called["n"] == 0  # 未调用模型

    # A 自己的会话可以进入（mock 返回），并在响应中保留会话 ID
    ca = _create_conv(client, hdr_a, "mine")
    body["conversation_id"] = ca
    r = client.post("/chat/chat/completions", headers=hdr_a, json=body)
    assert r.status_code == 200
    assert r.json().get("conversation_id") == ca


# ---------------------------------------------------------------------------
# owner 正确时消息创建和回答更新使用同一会话
# ---------------------------------------------------------------------------


def test_add_and_update_message_same_conversation(temp_user_db, secret):
    _, a = _headers(temp_user_db, secret, "alice")
    S = temp_user_db["Session"]
    s = S()
    try:
        from chatchat.server.db.repository import create_conversation, get_owned_conversation

        conv = create_conversation(s, a["id"], "llm_chat", "c")
        mid = add_message(s, conv, a["id"], "llm_chat", "q", response="")
        update_message(s, mid, a["id"], response="a")

        m = s.get(MessageModel, mid)
        assert m is not None
        assert m.conversation_id == conv  # 同一条会话
        assert m.response == "a"
        # owner 视角可看到该消息所属会话
        assert get_owned_conversation(s, conv, a["id"]) is not None
        # 另一个 owner 看不到该消息
        from chatchat.server.db.repository.message_repository import _owned_message

        assert _owned_message(s, mid, "someone-else") is None
    finally:
        s.close()


def test_chat_owner_correct_creates_message_in_same_conversation(
    client, temp_user_db, secret, monkeypatch
):
    import chatchat.server.api_server.chat_routes as cr

    async def fake_chat(*args, **kwargs):
        return {"choices": []}

    monkeypatch.setattr(cr, "chat", fake_chat)

    hdr_a, a = _headers(temp_user_db, secret, "alice")
    ca = _create_conv(client, hdr_a, "mine")
    r = client.post(
        "/chat/chat/completions",
        headers=hdr_a,
        json={
            "model": "qwen:7b",
            "stream": False,
            "messages": [{"role": "user", "content": "hello"}],
            "conversation_id": ca,
        },
    )
    assert r.status_code == 200
    s = temp_user_db["Session"]()
    try:
        msgs = s.query(MessageModel).filter_by(conversation_id=ca).all()
        assert len(msgs) == 1
        assert msgs[0].query == "hello"
        assert r.json().get("conversation_id") == ca
    finally:
        s.close()


# ---------------------------------------------------------------------------
# 主聊天未登录 401 / 必须改密 403
# ---------------------------------------------------------------------------


def test_chat_completions_unlogged_401(client):
    r = client.post(
        "/chat/chat/completions",
        json={"model": "qwen:7b", "stream": False, "messages": [{"role": "user", "content": "hi"}]},
    )
    assert r.status_code == 401


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
