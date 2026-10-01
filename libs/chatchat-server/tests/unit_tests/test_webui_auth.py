"""任务 004 / 005 的 WebUI 认证状态与 Cookie 恢复纯单元测试。"""

from chatchat.webui_pages.auth_state import (
    COOKIE_INVALIDATED_KEY,
    CURRENT_CONVERSATION_ID_KEY,
    CURRENT_USER_KEY,
    CUR_CONV_NAME_KEY,
    FILE_CHAT_ID_KEY,
    TOKEN_KEY,
    clear_private_state,
    conversation_options,
    ensure_authenticated,
    mark_cookie_invalidated,
    messages_to_history,
    synchronize_current_conversation,
)
from chatchat.webui_pages import cookie_state
from chatchat.webui_pages.utils import ApiRequest, AuthenticationError


class FakeCookieManager:
    """离线 fake CookieManager：记录写入 / 删除，不启动浏览器或组件。"""

    def __init__(self, value=None):
        self.value = value
        self.set_calls = []
        self.clear_calls = 0

    def get(self, cookie):
        return self.value

    def set(self, cookie, val, key="set", max_age=None):
        self.set_calls.append((val, max_age))
        self.value = val

    def delete(self, cookie, key="delete"):
        self.clear_calls += 1
        self.value = None


class FakeBrokenCookieManager:
    """模拟组件调用异常。"""

    def get(self, cookie):
        raise RuntimeError("component unavailable")


class FakeApi:
    """离线 fake 已认证客户端：只模拟 ``me()`` 行为。"""

    def __init__(self, me_result=None, raise_auth=False):
        self.token = None
        self.me_result = me_result
        self.raise_auth = raise_auth

    def me(self):
        if self.raise_auth:
            raise AuthenticationError("401")
        return self.me_result


def test_api_request_merges_bearer_and_custom_headers():
    api = ApiRequest(base_url="http://example.test", token="token-a")
    assert api._auth_headers() == {"Authorization": "Bearer token-a"}
    assert api._auth_headers({"X-Test": "1"}) == {
        "X-Test": "1",
        "Authorization": "Bearer token-a",
    }
    assert api._auth_headers({"Authorization": "Bearer explicit"}) == {
        "Authorization": "Bearer explicit"
    }
    assert ApiRequest(base_url="http://example.test")._auth_headers() == {}


def test_clear_private_state_removes_previous_user_data():
    session = {
        TOKEN_KEY: "token-a",
        CURRENT_USER_KEY: {"id": "a"},
        CURRENT_CONVERSATION_ID_KEY: "conv-a",
        CUR_CONV_NAME_KEY: "conv-a",
        FILE_CHAT_ID_KEY: "file-a",
        "unrelated": "keep",
    }
    clear_private_state(session)
    assert session == {"unrelated": "keep"}


def test_selected_conversation_survives_streamlit_rerun():
    conversations = [
        {"id": "old", "name": "同名"},
        {"id": "new", "name": "同名"},
    ]
    session = {
        CURRENT_CONVERSATION_ID_KEY: "old",
        CUR_CONV_NAME_KEY: "new",
    }
    assert synchronize_current_conversation(session, conversations) == "new"
    assert session[CURRENT_CONVERSATION_ID_KEY] == "new"
    assert session[CUR_CONV_NAME_KEY] == "new"
    assert [item["id"] for item in conversation_options(conversations)] == [
        "old",
        "new",
    ]


def test_messages_restore_in_user_assistant_order():
    history = messages_to_history(
        [
            {"query": "q1", "response": "a1"},
            {"query": "q2", "response": "a2"},
        ]
    )
    assert history == [
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "q2"},
        {"role": "assistant", "content": "a2"},
    ]


# ---------------------------------------------------------------------------
# 任务 005：Cookie 写入 / 恢复 / 清理状态机（离线，fake CookieManager + fake API）
# ---------------------------------------------------------------------------

def test_save_token_cookie_writes_token_and_captures_expires_in():
    manager = FakeCookieManager()
    session = {}
    status = cookie_state.save_token_cookie(session, "tok-a", 1800, manager)
    assert status == "saved"
    # Cookie 只保存访问 Token，生命周期不超过 expires_in
    assert manager.set_calls == [("tok-a", 1800)]
    assert manager.value == "tok-a"
    # Cookie 适配层不把用户名 / 密码 / 完整用户对象写入 session 或 Cookie
    assert session == {}


def test_save_token_cookie_unavailable_when_manager_missing():
    session = {}
    status = cookie_state.save_token_cookie(session, "tok-a", 1800, manager=None)
    assert status in ("unavailable",)
    # 未安装组件时不抛异常，也不污染 session
    assert session == {}


def test_save_token_cookie_rejects_invalid_token():
    manager = FakeCookieManager()
    session = {}
    assert cookie_state.save_token_cookie(session, "", 1800, manager) == "unavailable"
    assert cookie_state.save_token_cookie(session, None, 1800, manager) == "unavailable"
    assert manager.set_calls == []


def test_resolve_login_token_prefers_session_state():
    manager = FakeCookieManager("cookie-token")
    session = {TOKEN_KEY: "session-token"}
    token, status = cookie_state.resolve_login_token(session, manager)
    assert token == "session-token"
    assert status == "session"
    # Session State 优先：绝不从 Cookie 覆盖
    assert session[TOKEN_KEY] == "session-token"


def test_resolve_login_token_restores_from_cookie_when_session_empty():
    manager = FakeCookieManager("cookie-token")
    session = {}
    token, status = cookie_state.resolve_login_token(session, manager)
    assert token == "cookie-token"
    assert status == "restored"
    assert session[TOKEN_KEY] == "cookie-token"


def test_resolve_login_token_no_token_when_cookie_empty():
    manager = FakeCookieManager(None)
    session = {}
    token, status = cookie_state.resolve_login_token(session, manager)
    assert token is None
    assert status == "no_token"
    assert TOKEN_KEY not in session


def test_resolve_login_token_unavailable_when_manager_fails():
    manager = FakeBrokenCookieManager()
    session = {}
    token, status = cookie_state.resolve_login_token(session, manager)
    assert token is None
    assert status == "unavailable"
    # 组件异常时不能误判为已登录，也不得恢复旧 Token
    assert TOKEN_KEY not in session


def test_resolve_login_token_respects_invalidated_flag():
    manager = FakeCookieManager("stale-token")
    session = {COOKIE_INVALIDATED_KEY: True}
    token, status = cookie_state.resolve_login_token(session, manager)
    assert token is None
    assert status == "no_token"
    assert TOKEN_KEY not in session


def test_sync_token_cookie_cleared_when_session_has_no_token():
    manager = FakeCookieManager("stale-token")
    session = {COOKIE_INVALIDATED_KEY: True}
    status = cookie_state.sync_token_cookie(session, None, manager)
    assert status == "cleared"
    # 仍有值 → 请求删除
    assert manager.clear_calls == 1
    assert manager.value is None


def test_sync_token_cookie_clears_invalidated_flag_when_cookie_confirmed_empty():
    manager = FakeCookieManager(None)  # Cookie 已确认为空
    session = {COOKIE_INVALIDATED_KEY: True}
    status = cookie_state.sync_token_cookie(session, None, manager)
    assert status == "cleared"
    assert manager.clear_calls == 0
    # Cookie 已空：解除「已作废」标记，下次刷新可正常恢复
    assert COOKIE_INVALIDATED_KEY not in session


def test_sync_token_cookie_noop_on_normal_rerun():
    manager = FakeCookieManager("tok-a")
    session = {TOKEN_KEY: "tok-a"}
    status = cookie_state.sync_token_cookie(session, 1800, manager)
    assert status == "noop"
    # 普通 rerun 不重复写 Cookie
    assert manager.set_calls == []


def test_sync_token_cookie_marks_synced_when_cookie_already_matches():
    manager = FakeCookieManager("tok-a")  # 刚从 Cookie 恢复
    session = {TOKEN_KEY: "tok-a"}
    status = cookie_state.sync_token_cookie(session, 1800, manager)
    assert status == "noop"
    assert manager.set_calls == []


def test_sync_token_cookie_saves_when_session_token_changes():
    manager = FakeCookieManager("old-token")
    session = {TOKEN_KEY: "new-token"}
    status = cookie_state.sync_token_cookie(session, 900, manager)
    assert status == "saved"
    assert manager.set_calls == [("new-token", 900)]


def test_cookie_does_not_store_username_password_or_user_object():
    """登录成功只把访问 Token 写入 Cookie；用户名 / 密码 / 用户对象不落 Cookie。"""
    manager = FakeCookieManager()
    session = {}
    user = {"username": "alice", "password": "secret", "id": 1}
    # 模拟 render_login 成功路径：只传 token 给 save_token_cookie
    cookie_state.save_token_cookie(session, "tok-a", 1800, manager)
    # Cookie 内容只包含 token，不含任何用户字段
    assert manager.value == "tok-a"
    for secret in ("alice", "secret", "tok-a"):
        if secret == "tok-a":
            continue
        assert secret not in str(manager.value)
    # 用户对象绝不被序列化进 Cookie
    assert "alice" not in str(manager.value)
    assert "secret" not in str(manager.value)
    assert "1" not in str(manager.value) or manager.value == "tok-a"


def test_mark_cookie_invalidated_blocks_restoration_until_cleared():
    session = {}
    mark_cookie_invalidated(session)
    assert session.get(COOKIE_INVALIDATED_KEY) is True
    manager = FakeCookieManager("tok-a")
    # 作废标记期间无法从 Cookie 恢复
    token, status = cookie_state.resolve_login_token(session, manager)
    assert token is None
    assert status == "no_token"
    # 删除 Cookie 后标记解除，下次可恢复
    manager.delete(cookie_state.COOKIE_NAME)
    manager.value = None
    cookie_state.sync_token_cookie(session, None, manager)
    assert COOKIE_INVALIDATED_KEY not in session


def test_expired_token_via_me_failure_clears_cookie_and_state():
    """刷新恢复的 Token 经 /auth/me 失败：同时清除 Cookie 与私有状态。"""
    manager = FakeCookieManager("expired-token")
    session = {}
    token, status = cookie_state.resolve_login_token(session, manager)
    assert status == "restored"
    assert session[TOKEN_KEY] == "expired-token"
    # /auth/me 失败（过期 / 禁用 / 用户已失效）
    api = FakeApi(raise_auth=True)
    user = ensure_authenticated(session, api)
    assert user is None
    # 私有状态已清理
    assert TOKEN_KEY not in session
    assert CURRENT_USER_KEY not in session
    # 再同步 Cookie：Session 无 Token → 删除 Cookie
    assert cookie_state.sync_token_cookie(session, None, manager) == "cleared"
    assert manager.clear_calls == 1


def test_valid_token_via_me_success_keeps_cookie():
    manager = FakeCookieManager("valid-token")
    session = {}
    token, status = cookie_state.resolve_login_token(session, manager)
    assert status == "restored"
    api = FakeApi(me_result={"username": "alice", "display_name": "Alice"})
    user = ensure_authenticated(session, api)
    assert user == {"username": "alice", "display_name": "Alice"}
    # 校验通过：Cookie 与 Session Token 保持一致
    assert cookie_state.sync_token_cookie(session, 1800, manager) == "noop"
    assert session[TOKEN_KEY] == "valid-token"
    assert manager.value == "valid-token"


def test_cookie_max_age_caps_at_expires_in():
    assert cookie_state._cookie_max_age(1800) == 1800
    assert cookie_state._cookie_max_age(60) == 60
    # 缺失 / 非法 → 安全上限
    assert cookie_state._cookie_max_age(None) == 60
    assert cookie_state._cookie_max_age(0) == 60
    assert cookie_state._cookie_max_age(-5) == 60
