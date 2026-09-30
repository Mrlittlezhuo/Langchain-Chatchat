import sys

import streamlit as st
import streamlit_antd_components as sac

from chatchat import __version__
from chatchat.server.utils import api_address
from chatchat.webui_pages.dialogue.dialogue import dialogue_page, clear_private_caches
from chatchat.webui_pages.kb_chat import kb_chat
from chatchat.webui_pages.mcp import mcp_management_page
from chatchat.webui_pages.knowledge_base.knowledge_base import knowledge_base_page
from chatchat.webui_pages.utils import *
from chatchat.webui_pages import auth_state
from chatchat.webui_pages.auth_state import (
    get_token,
    get_current_user,
    set_authenticated_state,
    clear_private_state,
    get_session_api,
    ensure_authenticated,
)

# 跨用户共享的基础客户端：绝不保存任何用户 Token。
# 已认证请求统一使用 get_session_api() 返回的「本会话专用」客户端。
_base_api = ApiRequest(base_url=api_address())


def _do_login(username: str, password: str):
    """执行登录（POST /auth/login）。成功返回 {"token","user",...}，失败返回 None。"""
    api = ApiRequest(base_url=api_address())
    try:
        return api.login(username, password)
    except AuthenticationError:
        return None


def _do_logout() -> None:
    """退出登录：尝试通知后端，但无论成败都清理本地用户私有状态。"""
    token = get_token(st.session_state)
    if token:
        api = get_session_api(st.session_state, api_address())
        try:
            api.logout()
        except Exception:
            # logout 是无状态幂等接口，失败不影响本地清理
            pass
    clear_private_state(st.session_state)
    try:
        clear_private_caches()
    except Exception:
        pass
    st.rerun()


def render_login() -> None:
    """未登录时的登录页（不渲染任何业务侧栏/页面）。"""
    st.subheader("登录")
    st.info("请登录以访问 Langchain-Chatchat")
    col1, col2 = st.columns([1, 1])
    username = col1.text_input("用户名")
    password = col2.text_input("密码", type="password")
    if st.button("登录", type="primary", use_container_width=True):
        if not username or not password:
            st.error("请输入用户名和密码")
        else:
            data = _do_login(username, password)
            if data:
                set_authenticated_state(
                    st.session_state, data["token"], data["user"]
                )
                st.rerun()
            else:
                st.error("登录失败：用户名或密码错误，或无法连接服务器")


def render_change_password(api: ApiRequest) -> None:
    """首次登录（must_change_password）时只显示改密表单，改完要求重新登录。"""
    st.subheader("首次登录需修改密码")
    st.info("出于安全考虑，请设置一个新密码后再进入系统")
    old = st.text_input("原密码", type="password")
    new = st.text_input("新密码", type="password")
    if st.button("修改密码", type="primary", use_container_width=True):
        if not old or not new:
            st.error("请输入原密码和新密码")
        else:
            try:
                api.change_password(old, new)
                # 改密成功后清除旧 Token，要求用新密码重新登录
                clear_private_state(st.session_state)
                try:
                    clear_private_caches()
                except Exception:
                    pass
                st.success("密码已修改，请使用新密码重新登录")
                st.rerun()
            except AuthenticationError:
                st.error("修改失败：原密码错误、Token 已失效或用户已被禁用")
            except Exception as e:
                st.error(f"修改失败：{e}")


def render_business_sidebar(api: ApiRequest, user: dict) -> str:
    """已登录时的业务侧栏：Logo、当前用户、退出登录、页面菜单。"""
    with st.sidebar:
        st.image(
            get_img_base64("logo-long-chatchat-trans-v2.png"), use_column_width=True
        )
        st.caption(
            f"""<p align="right">当前版本：{__version__}</p>""",
            unsafe_allow_html=True,
        )

        display_name = user.get("display_name") or user.get("username", "")
        username = user.get("username", "")
        st.info(f"当前用户：{display_name}" + (f"（{username}）" if username else ""))

        st.button(
            "退出登录",
            use_container_width=True,
            on_click=_do_logout,
        )

        sac.divider()

        selected_page = sac.menu(
            [
                sac.MenuItem("多功能对话", icon="chat"),
                sac.MenuItem("RAG 对话", icon="database"),
                sac.MenuItem("知识库管理", icon="hdd-stack"),
                sac.MenuItem("MCP 管理", icon="hdd-stack"),
            ],
            key="selected_page",
            open_index=0,
        )

    return selected_page


if __name__ == "__main__":
    is_lite = "lite" in sys.argv  # TODO: remove lite mode

    st.set_page_config(
        "Langchain-Chatchat WebUI",
        get_img_base64("chatchat_icon_blue_square_v2.png"),
        initial_sidebar_state="expanded",
        menu_items={
            "Get Help": "https://github.com/chatchat-space/Langchain-Chatchat",
            "Report a bug": "https://github.com/chatchat-space/Langchain-Chatchat/issues",
            "About": f"""欢迎使用 Langchain-Chatchat WebUI {__version__}！""",
        },
        layout="centered",
    )

    # 加宽侧栏的样式
    st.markdown(
        """
        <style>
        [data-testid="stSidebarUserContent"] {
            padding-top: 20px;
        }
        .block-container {
            padding-top: 25px;
        }
        [data-testid="stBottomBlockContainer"] {
            padding-bottom: 20px;
        }
        """,
        unsafe_allow_html=True,
    )

    # ------------------------------------------------------------------
    # 登录门禁：未登录只显示登录页，不渲染任何业务侧栏/页面（7.1）
    # ------------------------------------------------------------------
    token = get_token(st.session_state)
    if not token:
        render_login()
        st.stop()

    # 已登录：使用「本会话专用」已认证客户端，并校验 Token（7.1/7.2）
    api = get_session_api(st.session_state, api_address())
    user = ensure_authenticated(st.session_state, api)
    if user is None:
        # Token 无效/过期/用户已失效：状态已清理，回到登录页
        render_login()
        st.stop()

    # 首次登录：必须改完密码才能进入业务页（7.1）
    if user.get("must_change_password"):
        render_change_password(api)
        st.stop()

    # 业务页面
    selected_page = render_business_sidebar(api, user)

    if selected_page == "知识库管理":
        knowledge_base_page(api=api, is_lite=is_lite)
    elif selected_page == "RAG 对话":
        kb_chat(api=api)
    elif selected_page == "MCP 管理":
        mcp_management_page(api=api)
    else:
        dialogue_page(api=api, is_lite=is_lite)
