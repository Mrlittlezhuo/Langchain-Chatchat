"""WebUI 登录态与用户私有状态的辅助函数。

设计目标（对应任务文档 7.1 / 7.2 / 7.4）：
- 登录 Token 与当前用户只保存在 ``st.session_state`` 中；未登录不渲染任何业务页面。
- 401（未登录 / Token 过期 / 用户已失效）统一清理所有用户私有页面状态并回到登录页。
- 用户私有数据不进入跨用户共享的模块级 HTTP 客户端，也不进入不带用户 id 的缓存。

本模块只依赖 ``chatchat.webui_pages.utils``（ApiRequest / AuthenticationError），
不依赖 Streamlit 运行时，因此可在单元测试中用普通 dict / 假对象验证。
"""

from typing import Any, Callable, Dict, List, Optional, Tuple

from chatchat.webui_pages.utils import ApiRequest, AuthenticationError


# ---------------------------------------------------------------------------
# session_state 中用户私有数据的键名（7.4 统一清理清单）
# ---------------------------------------------------------------------------
TOKEN_KEY = "auth_token"
CURRENT_USER_KEY = "current_user"
SESSION_API_KEY = "_session_api"

# 会话（conversation，后端 id 为主键）
CONVERSATION_LIST_KEY = "conversation_list"
CURRENT_CONVERSATION_ID_KEY = "current_conversation_id"
LAST_CONVERSATION_ID_KEY = "last_conversation_id"
LOADED_CONVERSATION_IDS_KEY = "loaded_conversation_ids"
LOADED_CONVERSATION_ID_KEY = "loaded_conversation_id"

# 旧 name 主键（kb_chat 仍使用；统一清理时一并清除）
CUR_CONV_NAME_KEY = "cur_conv_name"
LAST_CONV_NAME_KEY = "last_conv_name"

# ChatBox 历史 / 上下文（键为会话 id）
CHAT_HISTORY_KEY = "chat_history"

# 图片
UPLOAD_IMAGE_KEY = "upload_image"
CUR_IMAGE_KEY = "cur_image"
PASTE_IMAGE_KEY = "paste_image"

# 文件对话
FILE_CHAT_ID_KEY = "file_chat_id"

# Agent / 工具 / MCP 选择
USE_AGENT_KEY = "use_agent"
USE_MCP_KEY = "use_mcp"
SELECTED_TOOLS_KEY = "selected_tools"

# 模型 / RAG 配置
SYSTEM_MESSAGE_KEY = "system_message"
LLM_MODEL_KEY = "llm_model"
PLATFORM_KEY = "platform"
TEMPERATURE_KEY = "temperature"
PROMPT_KEY = "prompt"
HISTORY_LEN_KEY = "history_len"
SELECTED_KB_KEY = "selected_kb"
KB_TOP_K_KEY = "kb_top_k"
SE_TOP_K_KEY = "se_top_k"
SCORE_THRESHOLD_KEY = "score_threshold"
SEARCH_ENGINE_KEY = "search_engine"
RETURN_DIRECT_KEY = "return_direct"

#: 退出 / 401 时必须清除的所有用户私有键（最小集合）。
PRIVATE_STATE_KEYS: List[str] = [
    TOKEN_KEY,
    CURRENT_USER_KEY,
    SESSION_API_KEY,
    CONVERSATION_LIST_KEY,
    CURRENT_CONVERSATION_ID_KEY,
    LAST_CONVERSATION_ID_KEY,
    LOADED_CONVERSATION_IDS_KEY,
    LOADED_CONVERSATION_ID_KEY,
    CUR_CONV_NAME_KEY,
    LAST_CONV_NAME_KEY,
    CHAT_HISTORY_KEY,
    UPLOAD_IMAGE_KEY,
    CUR_IMAGE_KEY,
    PASTE_IMAGE_KEY,
    FILE_CHAT_ID_KEY,
    USE_AGENT_KEY,
    USE_MCP_KEY,
    SELECTED_TOOLS_KEY,
    SYSTEM_MESSAGE_KEY,
    LLM_MODEL_KEY,
    PLATFORM_KEY,
    TEMPERATURE_KEY,
    PROMPT_KEY,
    HISTORY_LEN_KEY,
    SELECTED_KB_KEY,
    KB_TOP_K_KEY,
    SE_TOP_K_KEY,
    SCORE_THRESHOLD_KEY,
    SEARCH_ENGINE_KEY,
    RETURN_DIRECT_KEY,
]


# ---------------------------------------------------------------------------
# 登录态读写
# ---------------------------------------------------------------------------
def get_token(session: Dict[str, Any]) -> Optional[str]:
    return session.get(TOKEN_KEY)


def get_current_user(session: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    user = session.get(CURRENT_USER_KEY)
    return user if isinstance(user, dict) else None


def set_authenticated_state(
    session: Dict[str, Any], token: str, user: Dict[str, Any]
) -> None:
    """登录成功后写入当前会话的 Token 与用户信息（仅本会话可见）。"""
    session[TOKEN_KEY] = token
    session[CURRENT_USER_KEY] = user


# ---------------------------------------------------------------------------
# 统一清理（7.4）
# ---------------------------------------------------------------------------
def clear_private_state(
    session: Dict[str, Any], keys: Optional[List[str]] = None
) -> None:
    """清除所有用户私有页面状态。

    退出登录 / Token 过期 / 用户已失效时调用，确保用户 A 的会话、历史、
    图片、文件、Agent/工具/MCP 选择等不会泄漏给用户 B。
    """
    for key in keys if keys is not None else PRIVATE_STATE_KEYS:
        session.pop(key, None)


# ---------------------------------------------------------------------------
# 当前会话专用已认证客户端（Token 仅存于本会话 session_state）
# ---------------------------------------------------------------------------
def get_session_api(
    session: Dict[str, Any], base_url: str
) -> ApiRequest:
    """返回当前会话专用的已认证 ApiRequest。

    该客户端实例保存在 ``session[SESSION_API_KEY]`` 中（仅本会话可见），
    绝不写入跨用户共享的模块级客户端，从而避免残留其他用户的 Token。
    Token 变化（重新登录 / 登出）时同步更新该实例。
    """
    token = get_token(session)
    api = session.get(SESSION_API_KEY)
    if api is None:
        api = ApiRequest(base_url=base_url, token=token)
        session[SESSION_API_KEY] = api
    else:
        api.token = token
    return api


# ---------------------------------------------------------------------------
# Token 校验（每次进入业务页面前）
# ---------------------------------------------------------------------------
def ensure_authenticated(
    session: Dict[str, Any], api: ApiRequest
) -> Optional[Dict[str, Any]]:
    """校验当前会话 Token。

    - 未登录：返回 None（调用方渲染登录页）。
    - 有效：``GET /auth/me`` 成功后更新 ``current_user``，返回用户信息。
    - 401 / 过期 / 用户已失效：清理所有用户私有状态，返回 None。
    """
    token = get_token(session)
    if not token:
        return None
    api.token = token
    try:
        user = api.me()
    except AuthenticationError:
        clear_private_state(session)
        return None
    if isinstance(user, dict):
        session[CURRENT_USER_KEY] = user
        return user
    return None


# ---------------------------------------------------------------------------
# 后端会话响应 → 页面选项（id 稳定键）
# ---------------------------------------------------------------------------
def conversation_options(
    backend_list: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """将后端会话列表映射为页面选项，每项含 ``id`` 与 ``name``。

    id 作为稳定键；同名会话因 id 不同而被区分。保持后端返回顺序
    （update_time DESC）。
    """
    options: List[Dict[str, Any]] = []
    for item in backend_list or []:
        if not isinstance(item, dict):
            continue
        conv_id = item.get("id")
        if conv_id is None:
            continue
        options.append({"id": conv_id, "name": item.get("name", "")})
    return options


def resolve_current_conversation(
    conversation_list: List[Dict[str, Any]], current_id: Optional[str]
) -> Optional[str]:
    """根据后端会话列表与当前 id，决定应使用的会话 id。

    - 当前 id 在列表中：返回当前 id。
    - 当前 id 无效但列表非空：返回列表第一个 id。
    - 列表为空：返回 None（调用方需创建默认会话）。
    """
    ids = [c.get("id") for c in conversation_list or [] if isinstance(c, dict)]
    if current_id is not None and current_id in ids:
        return current_id
    if ids:
        return ids[0]
    return None


def synchronize_current_conversation(
    session: Dict[str, Any], conversation_list: List[Dict[str, Any]]
) -> Optional[str]:
    """同步会话选择控件与当前后端会话 ID。

    Streamlit 会在 selectbox 变化后先把新值写入 ``cur_conv_name`` 再重跑。
    因此优先采用该值；仅当它不在后端列表中时才回退到原当前会话或列表
    第一项。这样不会在重跑开始时把用户刚选中的会话覆盖回旧值。
    """
    requested_id = session.get(CUR_CONV_NAME_KEY)
    current_id = session.get(CURRENT_CONVERSATION_ID_KEY)
    ids = [c.get("id") for c in conversation_list or [] if isinstance(c, dict)]
    candidate = requested_id if requested_id in ids else current_id
    resolved = resolve_current_conversation(conversation_list, candidate)
    if resolved is not None:
        session[CURRENT_CONVERSATION_ID_KEY] = resolved
        session[CUR_CONV_NAME_KEY] = resolved
    return resolved


def find_conversation_id_by_name(
    conversation_list: List[Dict[str, Any]], name: str
) -> Optional[str]:
    """按名称查找会话 id（用于兼容旧 name 主键逻辑；同取首个匹配）。"""
    for item in conversation_list or []:
        if isinstance(item, dict) and item.get("name") == name:
            return item.get("id")
    return None


# ---------------------------------------------------------------------------
# 后端历史消息 → ChatBox 历史（user / assistant 顺序）
# ---------------------------------------------------------------------------
def messages_to_history(
    backend_messages: List[Dict[str, Any]],
) -> List[Dict[str, str]]:
    """将后端 ``GET /conversations/{id}/messages`` 的返回映射为
    ``[{"role": "user", "content": ...}, {"role": "assistant", "content": ...}, ...]``。

    后端按 create_time ASC 返回；每条含 ``query``（用户）与 ``response``（助手）。
    输入顺序即为渲染顺序。
    """
    history: List[Dict[str, str]] = []
    for msg in backend_messages or []:
        if not isinstance(msg, dict):
            continue
        query = msg.get("query")
        response = msg.get("response")
        if query:
            history.append({"role": "user", "content": str(query)})
        if response:
            history.append({"role": "assistant", "content": str(response)})
    return history


def history_to_chat_history(
    conv_id: str,
    backend_messages: List[Dict[str, Any]],
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """构造 ChatBox 持久化结构 ``{conv_id: {"history": [...], "context": {...}}}``。

    ChatBox 的 ``history`` 元素形如 ``{"role","elements","metadata"}``；
    这里用纯 dict 保存角色与文本，供 WebUI 在运行时转成元素对象。
    """
    return {
        conv_id: {
            "history": [
                {
                    "role": item["role"],
                    "content": item["content"],
                    "metadata": {},
                }
                for item in messages_to_history(backend_messages)
            ],
            "context": dict(context) if context else {},
        }
    }
