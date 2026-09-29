"""FastAPI 认证依赖：``get_current_user`` / ``require_admin`` /
``require_password_changed``。

- Token 解码后每次按 ``sub`` 查询数据库并校验 active 与 auth_version；
- 过期/签名错误/用户不存在/禁用/版本不一致统一 401，带
  ``WWW-Authenticate: Bearer``；
- session 通过可覆盖的 ``get_db`` 依赖注入，便于测试指向临时
  数据库。
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from chatchat.server.db.models.user_model import UserModel
from chatchat.server.db.session import get_db
from chatchat.server.auth import jwt as jwt_mod

oauth2_scheme = HTTPBearer(auto_error=False)


def _unauthorized() -> None:
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="认证失败",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(oauth2_scheme),
    session: Session = Depends(get_db),
) -> UserModel:
    if credentials is None or credentials.scheme.lower() != "bearer":
        _unauthorized()
    try:
        claims = jwt_mod.decode_token(credentials.credentials)
    except jwt_mod.TokenValidationError:
        _unauthorized()
    user = (
        session.query(UserModel).filter(UserModel.id == claims["sub"]).one_or_none()
    )
    if user is None or user.status != "active" or user.auth_version != claims["ver"]:
        _unauthorized()
    return user


def require_password_changed(
    user: UserModel = Depends(get_current_user),
) -> UserModel:
    """供后续业务路由使用：要求用户已完成强制改密。"""
    if user.must_change_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="请先修改密码",
        )
    return user


def require_admin(
    user: UserModel = Depends(require_password_changed),
) -> UserModel:
    """管理员接口同时要求已完成首次/重置后的强制改密。"""
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限"
        )
    return user


__all__ = [
    "get_current_user",
    "require_admin",
    "require_password_changed",
    "oauth2_scheme",
]
