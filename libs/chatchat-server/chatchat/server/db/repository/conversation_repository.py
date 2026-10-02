"""会话 Repository（owner-aware）。

所有读写都必须同时校验 conversation.id 与 owner_id；owner 不匹配、
owner 为 NULL 或会话不存在时一律视为"不可见"（返回 None / 抛
``ConversationNotOwned``），不区分原因，避免会话枚举。
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from chatchat.server.db.models.conversation_model import ConversationModel


class ConversationNotOwned(Exception):
    """会话不存在或不属于指定用户（调用方映射 404）。"""


def create_conversation(
    session: Session,
    owner_id: str,
    chat_type: str,
    name: str = "",
    conversation_id: str | None = None,
) -> str:
    """新增会话；owner 由服务端写入，不接受客户端指定。"""
    if not owner_id:
        raise ValueError("owner_id 不能为空")
    if not conversation_id:
        conversation_id = uuid.uuid4().hex
    now = datetime.now()
    c = ConversationModel(
        id=conversation_id,
        chat_type=chat_type,
        name=name,
        owner_id=owner_id,
        create_time=now,
        update_time=now,
    )
    session.add(c)
    session.commit()
    return c.id


def list_conversations(session: Session, owner_id: str) -> list[ConversationModel]:
    """当前用户的会话列表，按 update_time 倒序（无时间者按 id 兜底）。"""
    return (
        session.query(ConversationModel)
        .filter(ConversationModel.owner_id == owner_id)
        .order_by(
            ConversationModel.update_time.desc(),
            ConversationModel.id.desc(),
        )
        .all()
    )


def get_owned_conversation(
    session: Session, conversation_id: str, owner_id: str
) -> ConversationModel | None:
    """同时按 id + owner_id 过滤；不满足返回 None。"""
    if not conversation_id or not owner_id:
        return None
    return (
        session.query(ConversationModel)
        .filter(
            ConversationModel.id == conversation_id,
            ConversationModel.owner_id == owner_id,
        )
        .one_or_none()
    )


def rename_owned_conversation(
    session: Session, conversation_id: str, owner_id: str, name: str
) -> ConversationModel:
    """重命名自己的会话；不可见会话抛 ConversationNotOwned。"""
    c = get_owned_conversation(session, conversation_id, owner_id)
    if c is None:
        raise ConversationNotOwned(conversation_id)
    c.name = name
    c.update_time = datetime.now()
    session.commit()
    return c


def delete_owned_conversation(
    session: Session, conversation_id: str, owner_id: str
) -> None:
    """删除自己的会话及其全部消息；不可见会话抛 ConversationNotOwned。"""
    c = get_owned_conversation(session, conversation_id, owner_id)
    if c is None:
        raise ConversationNotOwned(conversation_id)
    # 同事务内先删消息再删会话
    from chatchat.server.db.models.message_model import MessageModel

    session.query(MessageModel).filter(
        MessageModel.conversation_id == conversation_id
    ).delete(synchronize_session=False)
    session.delete(c)
    session.commit()


__all__ = [
    "ConversationNotOwned",
    "create_conversation",
    "list_conversations",
    "get_owned_conversation",
    "rename_owned_conversation",
    "delete_owned_conversation",
]
