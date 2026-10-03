"""会话摘要 Repository（owner-aware）。

每会话至多一行摘要。摘要不是长期事实；长期召回只读 ``memory`` 表。
会话已按用户隔离，这里仍传 owner_id 做双重校验。
"""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from chatchat.server.db.models.session_summary_model import SessionSummaryModel


def get_session_summary(
    session: Session, conversation_id: str, owner_id: str
) -> SessionSummaryModel | None:
    """按会话取摘要（owner 不匹配/无会话返回 None）。"""
    if not conversation_id or not owner_id:
        return None
    return (
        session.query(SessionSummaryModel)
        .filter(
            SessionSummaryModel.conversation_id == conversation_id,
            SessionSummaryModel.owner_id == owner_id,
        )
        .one_or_none()
    )


def upsert_session_summary(
    session: Session,
    owner_id: str,
    conversation_id: str,
    summary: str,
    summarized_message_id: str | None = None,
    summarized_count: int = 0,
) -> SessionSummaryModel:
    """新增或更新会话摘要（每会话一行）。"""
    if not owner_id or not conversation_id:
        raise ValueError("owner_id 与 conversation_id 不能为空")
    row = (
        session.query(SessionSummaryModel)
        .filter(
            SessionSummaryModel.conversation_id == conversation_id,
            SessionSummaryModel.owner_id == owner_id,
        )
        .one_or_none()
    )
    if row is None:
        row = SessionSummaryModel(
            id=uuid.uuid4().hex,
            owner_id=owner_id,
            conversation_id=conversation_id,
            summary=summary or "",
            summarized_message_id=summarized_message_id,
            summarized_count=max(0, int(summarized_count)),
        )
        session.add(row)
    else:
        row.summary = summary or ""
        row.summarized_message_id = summarized_message_id
        row.summarized_count = max(0, int(summarized_count))
    session.commit()
    session.refresh(row)
    return row


def delete_session_summary(
    session: Session, conversation_id: str, owner_id: str
) -> None:
    """删除会话摘要（会话删除时一并清理）。"""
    if not conversation_id or not owner_id:
        return
    session.query(SessionSummaryModel).filter(
        SessionSummaryModel.conversation_id == conversation_id,
        SessionSummaryModel.owner_id == owner_id,
    ).delete(synchronize_session=False)
    session.commit()


__all__ = [
    "get_session_summary",
    "upsert_session_summary",
    "delete_session_summary",
]
