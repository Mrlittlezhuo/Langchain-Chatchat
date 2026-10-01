"""WebUI 登录 Token 的浏览器 Cookie 适配层（任务 005，7.1）。

设计要点：

- Cookie 只保存访问 Token（绝不写入用户名、密码或完整用户对象）。
- Cookie 名使用项目专用固定名称（``COOKIE_NAME``），避免与其他应用冲突。
- Cookie 生命周期不超过登录响应的 ``expires_in``。
- 具体 CookieManager（extra-streamlit-components）调用全部封装在本模块，
  业务页面不散落组件细节。
- 组件构造通过 ``make_cookie_manager`` / 各函数的 ``manager`` 参数可注入：
  单元测试传入 fake CookieManager，不启动浏览器、网络或 Streamlit 运行时；
  真实组件未安装 / 不可用时返回 None，由页面侧退化为 Session State 行为
  并给出可理解提示（7.3）。

使用的 CookieManager API（extra-streamlit-components 0.1.71）：

    cm = CookieManager(key=...)
    value = cm.get(cookie_name)
    cm.set(cookie_name, value, max_age=...)
    cm.delete(cookie_name)
"""

from typing import Any, Dict, Optional, Tuple

from chatchat.webui_pages.auth_state import (
    COOKIE_INVALIDATED_KEY,
    TOKEN_KEY,
)

#: 项目专用固定 Cookie 名（7.1）。
COOKIE_NAME = "chatchat_auth_token"

#: Cookie 组件不可用时退化为手动登录的可理解提示（7.3）。
COOKIE_UNAVAILABLE_MESSAGE = (
    "浏览器登录 Cookie 组件当前不可用：本次只能手动登录，"
    "刷新页面后需要重新登录。"
)

#: 登录响应缺少 expires_in 时使用的安全上限（秒）。
_DEFAULT_MAX_AGE_SECONDS = 60


def make_cookie_manager() -> Optional[Any]:
    """创建真实 CookieManager；组件缺失或构造失败时返回 None。

    页面侧每次脚本执行调用一次，并把返回的实例传给 ``resolve_login_token`` /
    ``sync_token_cookie``，保证同一次执行内组件只构造一次。
    """
    try:
        import extra_streamlit_components as stx
    except Exception:
        return None
    try:
        return stx.CookieManager(key=f"{COOKIE_NAME}_manager")
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 组件调用包装（隔离组件细节、吞掉组件层异常，保证页面侧可离线退化）
# ---------------------------------------------------------------------------
def _get_value(manager: Any) -> Tuple[bool, Optional[str]]:
    """读取项目 Cookie，返回 ``(是否成功, 值)``。"""
    try:
        value = manager.get(COOKIE_NAME)
    except Exception:
        return False, None
    if value is None:
        return True, None
    return True, str(value) or None


def _set_value(manager: Any, token: str, expires_in: Optional[int]) -> bool:
    max_age = _cookie_max_age(expires_in)
    try:
        manager.set(
            cookie=COOKIE_NAME,
            val=token,
            key=f"{COOKIE_NAME}_set",
            max_age=max_age,
        )
        return True
    except Exception:
        return False


def _clear(manager: Any) -> bool:
    try:
        manager.delete(COOKIE_NAME, key=f"{COOKIE_NAME}_delete")
        return True
    except Exception:
        return False


def _cookie_max_age(expires_in: Optional[int]) -> int:
    """Cookie 生命周期不超过登录响应的 ``expires_in``（7.1）。"""
    if isinstance(expires_in, (int, float)) and expires_in > 0:
        return int(expires_in)
    return _DEFAULT_MAX_AGE_SECONDS


# ---------------------------------------------------------------------------
# 登录态解析与 Cookie 同步（页面初始化状态机，7.2 / 7.3）
# ---------------------------------------------------------------------------
def resolve_login_token(
    session: Dict[str, Any], manager: Optional[Any] = None
) -> Tuple[Optional[str], str]:
    """按页面初始化顺序读取登录 Token（7.2）。

    返回 ``(token, status)``：

    - ``("...", "session")``     Session State 已有 Token（最高优先级，不读 Cookie）；
    - ``("...", "restored")``    Session State 无 Token，已从 Cookie 恢复并写入 Session State；
    - ``(None, "no_token")``     Session State 无 Token，Cookie 为空；
    - ``(None, "unavailable")``  Cookie 组件不可用或调用失败，页面退化为手动登录。

    若 ``COOKIE_INVALIDATED_KEY`` 置位（退出 / 改密成功后、Cookie 尚未真正删除），
    返回 ``(None, "no_token")``，阻止旧 Token 被恢复。

    本函数只恢复 Token，不做校验；调用方仍须调用 ``ensure_authenticated``
    （GET /auth/me），失败时清除 Cookie 与私有 Session State。
    """
    token = session.get(TOKEN_KEY)
    if token:
        return token, "session"

    # 退出 / 改密成功后置位的「旧 Cookie 已作废」标记：在 Cookie 真正删除前，
    # 阻止旧 Token 被恢复回 Session State。
    if session.get(COOKIE_INVALIDATED_KEY):
        return None, "no_token"

    if manager is None:
        manager = make_cookie_manager()
    if manager is None:
        return None, "unavailable"

    read_ok, value = _get_value(manager)
    if not read_ok:
        return None, "unavailable"
    if value is None:
        return None, "no_token"

    # 恢复 Token 到 Session State；用户信息仍通过 /auth/me 获取
    session[TOKEN_KEY] = value
    return value, "restored"


def save_token_cookie(
    session: Dict[str, Any],
    token: str,
    expires_in: Optional[int] = None,
    manager: Optional[Any] = None,
) -> str:
    """登录成功时把访问 Token 写入 Cookie（7.2）。

    Cookie 只保存访问 Token；生命周期不超过 ``expires_in``。
    返回 ``"saved"``；组件不可用时返回 ``"unavailable"``（退化为仅 Session State）。
    """
    if not token or not isinstance(token, str):
        return "unavailable"
    if manager is None:
        manager = make_cookie_manager()
    if manager is None:
        return "unavailable"

    if not _set_value(manager, token, expires_in):
        return "unavailable"
    # 新的登录 Cookie 已写入：解除旧的「已作废」标记，允许后续从 Cookie 恢复
    session.pop(COOKIE_INVALIDATED_KEY, None)
    return "saved"


def sync_token_cookie(
    session: Dict[str, Any],
    expires_in: Optional[int] = None,
    manager: Optional[Any] = None,
) -> str:
    """让 Cookie 与 Session State 的 Token 保持一致（幂等，7.3）。

    每次进入已登录页面时调用一次：

    - Session 无 Token（退出 / 改密成功 / 认证失效）：删除既有 Cookie，返回 ``"cleared"``；
    - Cookie 值已与 Session Token 一致（如刚从 Cookie 恢复）：返回 ``"noop"``；
    - 其他情况：把 Session Token 写入 Cookie，返回 ``"saved"``。

    组件不可用时返回 ``"unavailable"``，页面退化为 Session State 行为。
    """
    token = session.get(TOKEN_KEY)
    if manager is None:
        manager = make_cookie_manager()
    if manager is None:
        return "unavailable"

    if not token:
        read_ok, cookie_value = _get_value(manager)
        if not read_ok:
            return "unavailable"
        if cookie_value is not None:
            # Cookie 仍有值：请求删除。保留「已作废」标记，
            # 直到下一次 sync 读到空 Cookie 时解除，避免删除未生效前被恢复。
            if not _clear(manager):
                return "unavailable"
        else:
            # Cookie 已确认为空：解除「已作废」标记，下次刷新可正常从 Cookie 恢复。
            session.pop(COOKIE_INVALIDATED_KEY, None)
        return "cleared"

    read_ok, cookie_value = _get_value(manager)
    if not read_ok:
        return "unavailable"
    if cookie_value == token:
        return "noop"

    if not _set_value(manager, token, expires_in):
        return "unavailable"
    return "saved"
