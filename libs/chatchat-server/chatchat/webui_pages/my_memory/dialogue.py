"""我的记忆（任务 007/008）：当前用户长期记忆的管理页面。

页面职责（WebUI）：
- 展示当前用户自己的记忆列表（后端只返回当前用户记忆）；
- 新增/编辑/删除记忆、设置启用状态、设置"自动记忆"开关；
- 对他人记忆的操作一律由后端返回 404，WebUI 不会把它误当成成功。

页面核心业务规则集中在 ApiRequest 的 memory_* 方法与后端路由；这里额外提供
一组**不依赖 streamlit/网络的纯函数**，便于离线单元测试：
- validate_memory_content / parse_memory_payload / memory_update_payload
- format_time / type_label / TYPE_OPTIONS
"""
import json
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import streamlit as st

from chatchat.webui_pages.utils import (
    ApiRequest,
    AuthenticationError,
    MemoryApiError,
)


# ---------------------------------------------------------------------------
# 记忆类型与展示映射（纯数据，便于测试）
# ---------------------------------------------------------------------------

#: 记忆类型 -> 中文标签
TYPE_LABELS: Dict[str, str] = {
    "fact": "事实",
    "preference": "偏好",
    "goal": "目标",
    "important": "重要事项",
}

#: 可选记忆类型（有序）
TYPE_OPTIONS: List[str] = ["fact", "preference", "goal", "important"]

#: 来源固定值（用户手动）
USER_SOURCE = "user"

#: 内容最大长度
MAX_CONTENT_LEN = 2000


def type_label(type: str) -> str:
    """记忆类型的中文标签；未知类型回退为原值。"""
    return TYPE_LABELS.get(type, type)


def validate_memory_content(content: Optional[str]) -> Tuple[bool, str]:
    """校验记忆内容：非空且不超过 MAX_CONTENT_LEN。"""
    if content is None:
        return False, "记忆内容不能为空"
    c = content.strip()
    if not c:
        return False, "记忆内容不能为空"
    if len(c) > MAX_CONTENT_LEN:
        return False, f"记忆内容过长（最多 {MAX_CONTENT_LEN} 字）"
    return True, ""


def parse_memory_payload(
    type: str,
    content: str,
    importance: int = 1,
    source: str = USER_SOURCE,
) -> Dict:
    """构造 POST /memories 的请求体（服务端据此创建当前用户记忆）。"""
    ok, _ = validate_memory_content(content)
    if not ok:
        raise ValueError("记忆内容无效")
    if type not in TYPE_LABELS:
        raise ValueError(f"未知记忆类型: {type}")
    importance = max(1, min(5, int(importance)))
    return {
        "type": type,
        "content": content.strip(),
        "importance": importance,
        "source": source,
    }


def memory_update_payload(fields: Dict) -> Dict:
    """构造 PATCH /memories/{id} 的请求体：只保留非 None 字段。"""
    out: Dict = {}
    for k, v in (fields or {}).items():
        if v is None:
            continue
        out[k] = v
    if "type" in out and out["type"] not in TYPE_LABELS:
        raise ValueError(f"未知记忆类型: {out['type']}")
    if "importance" in out:
        out["importance"] = max(1, min(5, int(out["importance"])))
    return out


def format_time(value) -> str:
    """把后端返回的 update_time（ISO 字符串或 datetime）格式化为可读时间。"""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M")
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return ""
        # 去掉可能的 'Z' 后缀
        s = s.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(s)
            return dt.strftime("%Y-%m-%d %H:%M")
        except ValueError:
            return s
    return str(value)


def memory_rows(memories: Optional[List[Dict]]) -> List[Dict]:
    """把后端记忆列表整理为展示行（保持后端顺序：update_time DESC）。

    纯函数，不触碰 streamlit/网络，便于测试。
    """
    rows: List[Dict] = []
    for m in (memories or []):
        conversation_id = m.get("source_conversation_id")
        message_id = m.get("source_message_id")
        if conversation_id or message_id:
            source_label = "来自会话"
            if conversation_id:
                source_label += f" {conversation_id[:8]}"
            if message_id:
                source_label += f" / 消息 {message_id[:8]}"
        else:
            source_label = "手动添加" if m.get("source") in {"user", "manual"} else "对话提取"
        rows.append(
            {
                "id": m.get("id"),
                "type": m.get("type"),
                "type_label": type_label(m.get("type")),
                "content": m.get("content"),
                "importance": m.get("importance"),
                "enabled": bool(m.get("enabled", True)),
                "source": m.get("source"),
                "source_label": source_label,
                "time": format_time(m.get("update_time") or m.get("create_time")),
            }
        )
    return rows


# ---------------------------------------------------------------------------
# streamlit 页面
# ---------------------------------------------------------------------------


def _add_memory_form(api: ApiRequest) -> None:
    with st.container():
        st.subheader("新增记忆")
        with st.form("add_memory"):
            mtype = st.selectbox("类型", TYPE_OPTIONS, format_func=type_label)
            importance = st.slider("重要度", 1, 5, 1)
            content = st.text_area("内容", max_chars=MAX_CONTENT_LEN)
            if st.form_submit_button("保存", type="primary"):
                ok, msg = validate_memory_content(content)
                if not ok:
                    st.error(msg)
                else:
                    try:
                        payload = parse_memory_payload(mtype, content, importance)
                        api.create_memory(**payload)
                        st.success("已保存")
                        st.rerun()
                    except (MemoryApiError, AuthenticationError) as e:
                        st.error(str(e))


def _toggle_auto_memory(api: ApiRequest) -> None:
    try:
        current = api.get_auto_memory()
    except (MemoryApiError, AuthenticationError):
        current = False
    with st.form("auto_memory"):
        st.caption(
            f"当前：{'已开启' if current else '已关闭'}。开启后会从对话中提取稳定信息；"
            "关闭后不做隐式提取，但「请记住/忘记」仍然生效。"
        )
        if st.form_submit_button("切换自动记忆"):
            try:
                api.set_auto_memory(not current)
                st.success(f"自动记忆已{'开启' if not current else '关闭'}")
                st.rerun()
            except (MemoryApiError, AuthenticationError) as e:
                st.error(str(e))


def _memory_list(api: ApiRequest) -> None:
    st.subheader("我的记忆")
    try:
        memories = api.list_memories()
    except (MemoryApiError, AuthenticationError) as e:
        st.error(str(e))
        return
    rows = memory_rows(memories)
    if not rows:
        st.info("还没有记忆。")
        return

    for i, r in enumerate(rows):
        col1, col2 = st.columns([4, 1])
        with col1:
            tag = "⚙️ " if not r["enabled"] else ""
            st.markdown(
                f"**{tag}{r['type_label']}**（重要度 {r['importance']}）"
                f"　{r['time']}"
            )
            st.write(r["content"])
            st.caption(r["source_label"])
        with col2:
            if st.button("编辑", key=f"edit_{i}"):
                _edit_memory(api, r)
            if st.button("删除", key=f"del_{i}"):
                try:
                    api.delete_memory(r["id"])
                    st.success("已删除")
                    st.rerun()
                except (MemoryApiError, AuthenticationError) as e:
                    st.error(str(e))
        st.divider()


def _edit_memory(api: ApiRequest, r: Dict) -> None:
    with st.container():
        with st.form(f"edit_form_{r['id']}"):
            etype = st.selectbox(
                "类型", TYPE_OPTIONS, index=TYPE_OPTIONS.index(r["type"]),
                format_func=type_label,
            )
            eimportance = st.slider("重要度", 1, 5, int(r["importance"] or 1))
            econtent = st.text_area("内容", value=r["content"], max_chars=MAX_CONTENT_LEN)
            eenabled = st.checkbox("启用", value=r["enabled"])
            ok, msg = validate_memory_content(econtent)
            if ok and st.form_submit_button("保存修改", type="primary"):
                try:
                    payload = memory_update_payload(
                        {
                            "type": etype,
                            "importance": eimportance,
                            "content": econtent,
                            "enabled": eenabled,
                        }
                    )
                    api.update_memory(r["id"], **payload)
                    st.success("已更新")
                    st.rerun()
                except (MemoryApiError, AuthenticationError) as e:
                    st.error(str(e))
            elif not ok:
                st.error(msg)


def my_memory_page(api: ApiRequest, is_lite: bool = False) -> None:
    """我的记忆页面入口。"""
    st.title("我的记忆")
    st.caption("管理当前用户的长期记忆。仅能查看/操作自己的记忆。")
    _toggle_auto_memory(api)
    st.divider()
    _add_memory_form(api)
    st.divider()
    _memory_list(api)
