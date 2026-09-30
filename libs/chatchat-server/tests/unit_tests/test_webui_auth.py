"""任务 004 的 WebUI 认证状态纯单元测试。"""

from chatchat.webui_pages.auth_state import (
    CURRENT_CONVERSATION_ID_KEY,
    CURRENT_USER_KEY,
    CUR_CONV_NAME_KEY,
    FILE_CHAT_ID_KEY,
    TOKEN_KEY,
    clear_private_state,
    conversation_options,
    messages_to_history,
    synchronize_current_conversation,
)
from chatchat.webui_pages.utils import ApiRequest


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
