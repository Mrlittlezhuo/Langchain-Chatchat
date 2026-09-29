"""消息反馈接口：要求登录，且只能反馈自己会话中的消息。"""
from fastapi import Body, Depends, HTTPException, status
from sqlalchemy.orm import Session

from chatchat.utils import build_logger
from chatchat.server.auth.deps import require_password_changed
from chatchat.server.db.models.user_model import UserModel
from chatchat.server.db.session import get_db
from chatchat.server.db.repository import (
    ConversationNotOwned,
    feedback_message,
)
from chatchat.server.utils import BaseResponse

logger = build_logger()


def chat_feedback(
    message_id: str = Body("", max_length=32, description="聊天记录id"),
    score: int = Body(0, max=100, description="用户评分，满分100，越大表示评价越高"),
    reason: str = Body("", description="用户评分理由，比如不符合事实等"),
    user: UserModel = Depends(require_password_changed),
    session: Session = Depends(get_db),
):
    try:
        feedback_message(session, message_id, user.id, score, reason)
    except ConversationNotOwned:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="聊天记录不存在或无权操作",
        )
    except Exception as e:
        msg = f"反馈聊天记录出错： {e}"
        logger.error(f"{e.__class__.__name__}: {msg}")
        return BaseResponse(code=500, msg=msg)

    return BaseResponse(code=200, msg=f"已反馈聊天记录 {message_id}")
