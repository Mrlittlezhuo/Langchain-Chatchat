"""RAG WebUI 的无状态数据转换函数。"""

from typing import Dict, List


def rag_conversation_options(conversations: List[Dict]) -> List[Dict]:
    """只保留 RAG 会话，避免普通聊天与 RAG 页面互相切换会话。"""
    return [
        {"id": item.get("id"), "name": item.get("name") or "RAG 会话"}
        for item in conversations or []
        if isinstance(item, dict)
        and item.get("id")
        and item.get("chat_type") == "kb_chat"
    ]


def reference_markdown(metadata: Dict) -> str:
    """把消息元数据中的结构化引用转换成恢复历史时使用的 Markdown。"""
    metadata = metadata or {}
    references = metadata.get("references") or []
    blocks = []
    for ref in references:
        index = ref.get("index", len(blocks) + 1)
        filename = ref.get("file_name") or "未知来源"
        url = ref.get("url") or ""
        title = f"[{filename}]({url})" if url else filename
        details = []
        if ref.get("page") is not None:
            details.append(f"页码 {ref['page']}")
        if isinstance(ref.get("score"), (int, float)):
            details.append(f"检索分数 {ref['score']:.4f}")
        suffix = f"（{'，'.join(details)}）" if details else ""
        blocks.append(
            f"出处 [{index}] {title}{suffix}\n\n{ref.get('content') or ''}"
        )
    if blocks:
        return "\n\n".join(blocks)
    legacy_docs = metadata.get("docs") or []
    if legacy_docs:
        return "\n\n".join(str(doc) for doc in legacy_docs)
    if metadata.get("retrieval_status") == "empty":
        return "未检索到符合条件的资料；该回答来自模型自身知识。"
    if metadata.get("retrieval_status") == "error":
        return f"检索失败：{metadata.get('error') or '未知错误'}"
    return ""


def rag_history_items(messages: List[Dict]) -> List[Dict]:
    """把后端消息转换成不依赖 Streamlit 的 RAG 历史描述。"""
    history = []
    for message in messages or []:
        if not isinstance(message, dict):
            continue
        if message.get("query"):
            history.append({"role": "user", "content": str(message["query"])})
        metadata = message.get("metadata") or {}
        response = str(message.get("response") or "")
        references = reference_markdown(metadata)
        if response or references:
            history.append(
                {
                    "role": "assistant",
                    "content": response,
                    "references": references,
                    "message_id": message.get("id"),
                }
            )
    return history
