from sqlalchemy import JSON, Column, DateTime, Index, Integer, String, func

from chatchat.server.db.base import Base


class ConversationModel(Base):
    """
    聊天记录模型
    """

    __tablename__ = "conversation"
    __table_args__ = (
        Index("ix_conversation_owner_update_time", "owner_id", "update_time"),
    )
    id = Column(String(32), primary_key=True, comment="对话框ID")
    name = Column(String(50), comment="对话框名称")
    chat_type = Column(String(50), comment="聊天类型")
    owner_id = Column(String(32), comment="所属用户ID")
    create_time = Column(DateTime, default=func.now(), comment="创建时间")
    update_time = Column(DateTime, comment="最后活动时间")

    def __repr__(self):
        return (
            f"<Conversation(id='{self.id}', name='{self.name}', "
            f"chat_type='{self.chat_type}', owner_id='{self.owner_id}', "
            f"create_time='{self.create_time}', update_time='{self.update_time}')>"
        )
