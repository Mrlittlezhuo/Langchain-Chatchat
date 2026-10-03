from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Integer,
    String,
    UniqueConstraint,
    func,
)

from chatchat.server.db.base import Base


class SessionSummaryModel(Base):
    """
    会话短期摘要（每会话一行），用于把"超出窗口"的较早历史压缩成一段
    可持续更新的摘要，避免每轮重复总结全部历史。

    - 短期上下文仍由最近若干轮原始消息（``filter_message``）构成，本表
      不替代它；模型注入时两者并存（摘要在前、近期轮次在后）。
    - ``summarized_message_id`` / ``summarized_count`` 记录摘要覆盖到的
      消息位置；后续只对新增消息做增量摘要，避免重复总结。
    - 会话摘要不是长期事实：长期召回只读 ``memory`` 表，不把本表当持久记忆。
    - 摘要按会话隔离（会话已按用户隔离），owner_id 冗余便于按用户直查。
    """

    __tablename__ = "session_summary"
    __table_args__ = (
        UniqueConstraint("conversation_id", name="uq_session_summary_conversation"),
        CheckConstraint("summarized_count >= 0", name="ck_session_summary_count"),
    )

    id = Column(String(32), primary_key=True, comment="摘要记录ID")
    owner_id = Column(
        String(32),
        nullable=False,
        index=True,
        comment="所属用户ID（会话属主的冗余记录）",
    )
    conversation_id = Column(
        String(32),
        nullable=False,
        index=True,
        comment="会话ID",
    )
    summary = Column(String(4000), nullable=False, default="", comment="压缩后的较早内容摘要")
    summarized_message_id = Column(
        String(32), nullable=True, comment="摘要覆盖到的最后一条消息ID（位置标记）"
    )
    summarized_count = Column(
        Integer, nullable=False, default=0, comment="摘要覆盖的消息数"
    )
    create_time = Column(DateTime, default=func.now(), comment="创建时间")
    update_time = Column(DateTime, default=func.now(), onupdate=func.now(), comment="更新时间")

    def __repr__(self):
        return (
            f"<SessionSummary(conversation_id='{self.conversation_id}', "
            f"owner_id='{self.owner_id}', summarized_count={self.summarized_count})>"
        )


__all__ = ["SessionSummaryModel"]
