"""用户账户 Repository（纯数据访问）。

所有方法接受显式 SQLAlchemy ``Session``，不使用全局 SessionLocal，
以便测试指向临时数据库。事务提交由上层 service 控制。
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from chatchat.server.db.models.user_model import UserModel


def _new_id() -> str:
    return uuid.uuid4().hex


def create_user(
    session: Session,
    *,
    username: str,
    display_name: str,
    password_hash: str,
    role: str = "user",
    status: str = "active",
    must_change_password: bool = True,
    auth_version: int = 1,
) -> UserModel:
    now = datetime.utcnow()
    user = UserModel(
        id=_new_id(),
        username=username,
        display_name=display_name,
        password_hash=password_hash,
        role=role,
        status=status,
        must_change_password=must_change_password,
        auth_version=auth_version,
        create_time=now,
        update_time=now,
    )
    session.add(user)
    session.flush()
    return user


def get_by_username(session: Session, username: str) -> Optional[UserModel]:
    return session.query(UserModel).filter(UserModel.username == username).one_or_none()


def get_by_id(session: Session, user_id: str) -> Optional[UserModel]:
    return session.query(UserModel).filter(UserModel.id == user_id).one_or_none()


def list_users(session: Session) -> List[UserModel]:
    return session.query(UserModel).order_by(UserModel.create_time).all()


def count_by_role(session: Session, role: str) -> int:
    return session.query(UserModel).filter(UserModel.role == role).count()


def has_admin(session: Session) -> bool:
    return count_by_role(session, "admin") > 0


__all__ = [
    "create_user",
    "get_by_username",
    "get_by_id",
    "list_users",
    "count_by_role",
    "has_admin",
]
