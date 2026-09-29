"""管理员用户管理路由：/admin/users（列表/创建/状态/重置密码）。

仅 admin 可访问；响应不含 password_hash / 明文密码 / JWT 密钥。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from chatchat.server.db.session import get_db
from chatchat.server.auth import service
from chatchat.server.auth.deps import require_admin
from chatchat.server.auth.schemas import (
    CreateUserRequest,
    ResetPasswordRequest,
    SetStatusRequest,
    UserOut,
)
from chatchat.server.db.models.user_model import UserModel

from .routes_auth import _user_out


admin_router = APIRouter(prefix="/admin", tags=["Admin"])


@admin_router.get("/users", summary="列出所有用户")
def list_users(
    admin: UserModel = Depends(require_admin), session: Session = Depends(get_db)
) -> list[UserOut]:
    return [_user_out(u) for u in service.list_users(session)]


@admin_router.post(
    "/users",
    summary="创建用户（密码不回显）",
    status_code=201,
)
def create_user(
    body: CreateUserRequest,
    admin: UserModel = Depends(require_admin),
    session: Session = Depends(get_db),
) -> UserOut:
    try:
        user = service.create_user(
            session,
            username=body.username,
            display_name=body.display_name,
            password=body.password.get_secret_value(),
            role=body.role,
        )
    except service.UsernameConflict:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="username 已存在",
        )
    except service.InvalidInput as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    session.commit()
    return _user_out(user)


@admin_router.patch("/users/{user_id}/status", summary="启用/禁用用户")
def set_status(
    user_id: str,
    body: SetStatusRequest,
    admin: UserModel = Depends(require_admin),
    session: Session = Depends(get_db),
) -> UserOut:
    try:
        user = service.set_status(session, admin, user_id, body.status)
    except service.UserNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在",
        )
    except service.Forbidden:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="不能禁用自己",
        )
    except service.NoAdminLeft:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="不能禁用最后一个 active 管理员",
        )
    except service.InvalidInput as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    session.commit()
    return _user_out(user)


@admin_router.post(
    "/users/{user_id}/reset-password",
    summary="重置用户密码（不回显）",
)
def reset_password(
    user_id: str,
    body: ResetPasswordRequest,
    admin: UserModel = Depends(require_admin),
    session: Session = Depends(get_db),
) -> UserOut:
    try:
        user = service.reset_password(
            session,
            admin,
            user_id,
            body.password.get_secret_value(),
        )
    except service.UserNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在",
        )
    except service.InvalidInput as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    session.commit()
    return _user_out(user)


__all__ = ["admin_router"]
