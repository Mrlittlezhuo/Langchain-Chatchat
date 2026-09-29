"""用户/认证业务 service（纯业务逻辑，接受显式 ``Session``）。

HTTP/CLI 层负责把这里的业务异常映射到稳定错误码；
service 不直接抛 HTTP 异常，便于离线测试。
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import List

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from chatchat.server.db.repository import user_repository as user_repo
from chatchat.server.db.models.user_model import UserModel
from chatchat.server.auth import password as pw


class UserError(Exception):
    """用户/认证业务错误基类。"""


class UsernameConflict(UserError):
    """重复 username（映射 409）。"""


class UserNotFound(UserError):
    """目标用户不存在（映射 404）。"""


class InvalidInput(UserError):
    """输入非法（映射 422）。"""


class AuthFailed(UserError):
    """认证失败：密码错误/未知用户/disabled（统一 401）。"""


class Forbidden(UserError):
    """权限不足（映射 403）。"""


class NoAdminLeft(UserError):
    """操作会导致系统没有 active admin（映射 422/400）。"""


#: 规范化 username：3–64，仅 a-z 0-9 . _ -
_USERNAME_RE = re.compile(r"^[a-z0-9._-]{3,64}$")

ROLES = ("admin", "user")
STATUSES = ("active", "disabled")


def normalize_username(raw: str) -> str:
    """去除首尾空白、转小写；非法抛 InvalidInput。"""
    if not isinstance(raw, str):
        raise InvalidInput("username 必须为字符串")
    username = raw.strip().lower()
    if not _USERNAME_RE.match(username):
        raise InvalidInput(
            "username 非法：去除首尾空白并转小写后需为 3–64 位，"
            "仅允许 a-z、0-9、.、_、-"
        )
    return username


def _new_user(
    session: Session,
    *,
    username: str,
    display_name: str,
    password: str,
    role: str = "user",
    status: str = "active",
    must_change_password: bool = True,
) -> UserModel:
    username = normalize_username(username)
    if role not in ROLES:
        raise InvalidInput(f"role 必须为 {'/'.join(ROLES)}")
    if status not in STATUSES:
        raise InvalidInput(f"status 必须为 {'/'.join(STATUSES)}")
    if not isinstance(display_name, str) or not display_name.strip():
        raise InvalidInput("display_name 不能为空")
    display_name = display_name.strip()
    if len(display_name) > 100:
        raise InvalidInput("display_name 不能超过 100 个字符")
    try:
        password_hash = pw.hash_password(password)
    except pw.PasswordValidationError as exc:
        raise InvalidInput(str(exc)) from exc
    try:
        with session.begin_nested():
            user = user_repo.create_user(
                session,
                username=username,
                display_name=display_name,
                password_hash=password_hash,
                role=role,
                status=status,
                must_change_password=must_change_password,
                auth_version=1,
            )
    except IntegrityError as exc:
        # SAVEPOINT 已回滚，外层 Session 仍可安全复用。
        # 当前 schema 唯一业务冲突为规范化 username。
        raise UsernameConflict(f"username 已存在: {username}") from exc
    return user


# ---------------------------------------------------------------------------
# 认证
# ---------------------------------------------------------------------------


def authenticate(
    session: Session,
    username: str,
    password: str,
) -> UserModel:
    """校验用户名和密码并确认 active；失败统一抛 AuthFailed。"""
    normalized = normalize_username(username)
    user = user_repo.get_by_username(session, normalized)
    if user is None:
        pw.dummy_verify()  # 对齐耗时，降低用户名枚举时序差异
        raise AuthFailed("用户名或密码错误")
    if not pw.verify_password(password, user.password_hash):
        raise AuthFailed("用户名或密码错误")
    if user.status != "active":
        raise AuthFailed("用户名或密码错误")
    return user


# ---------------------------------------------------------------------------
# 管理员引导
# ---------------------------------------------------------------------------


def init_first_admin(
    session: Session, username: str, display_name: str, password: str
) -> UserModel:
    """仅当不存在 admin 时创建首个管理员。"""
    if user_repo.has_admin(session):
        raise NoAdminLeft("系统已存在管理员，无法再次初始化")
    normalized = normalize_username(username)
    return _new_user(
        session,
        username=normalized,
        display_name=display_name,
        password=password,
        role="admin",
        status="active",
        must_change_password=True,
    )


# ---------------------------------------------------------------------------
# 用户管理（admin）
# ---------------------------------------------------------------------------


def list_users(session: Session) -> List[UserModel]:
    return user_repo.list_users(session)


def create_user(
    session: Session,
    username: str,
    display_name: str,
    password: str,
    role: str = "user",
) -> UserModel:
    return _new_user(
        session,
        username=normalize_username(username),
        display_name=display_name,
        password=password,
        role=role,
        status="active",
        must_change_password=True,
    )


def _require_user(session: Session, user_id: str) -> UserModel:
    user = user_repo.get_by_id(session, user_id)
    if user is None:
        raise UserNotFound(f"用户不存在: {user_id}")
    return user


def set_status(
    session: Session,
    actor: UserModel,
    user_id: str,
    status: str,
) -> UserModel:
    """禁用/启用用户；禁止自我禁用与禁用最后一个 active admin。"""
    if status not in STATUSES:
        raise InvalidInput(f"status 必须为 {'/'.join(STATUSES)}")
    target = _require_user(session, user_id)
    if status == "disabled":
        if target.id == actor.id:
            raise Forbidden("不能禁用自己")
        if target.role == "admin" and target.status == "active":
            active_admins = (
                session.query(UserModel)
                .filter(UserModel.role == "admin", UserModel.status == "active")
                .count()
            )
            if active_admins <= 1:
                raise NoAdminLeft("不能禁用最后一个 active 管理员")
    target.status = status
    # 禁用或重新启用都增加 auth_version，使旧 Token 立即失效；
    # 重新启用仍保留已经增加的版本
    target.auth_version += 1
    target.update_time = datetime.utcnow()
    session.flush()
    return target


def reset_password(
    session: Session, actor: UserModel, user_id: str, new_password: str
) -> UserModel:
    """管理员重置密码、要求用户改密并使旧 Token 失效。"""
    target = _require_user(session, user_id)
    try:
        password_hash = pw.hash_password(new_password)
    except pw.PasswordValidationError as exc:
        raise InvalidInput(str(exc)) from exc
    target.password_hash = password_hash
    target.must_change_password = True
    target.auth_version += 1
    target.update_time = datetime.utcnow()
    session.flush()
    return target


def change_password(
    session: Session, user: UserModel, old_password: str, new_password: str
) -> UserModel:
    """验证旧密码、更新密码并使旧 Token 失效。"""
    if not pw.verify_password(old_password, user.password_hash):
        raise AuthFailed("旧密码错误")
    try:
        password_hash = pw.hash_password(new_password)
    except pw.PasswordValidationError as exc:
        raise InvalidInput(str(exc)) from exc
    user.password_hash = password_hash
    user.must_change_password = False
    user.auth_version += 1
    user.update_time = datetime.utcnow()
    session.flush()
    return user


def is_active(session: Session, user_id: str, auth_version: int) -> bool:
    """get_current_user 用：确认用户存在、active 且版本匹配。"""
    user = user_repo.get_by_id(session, user_id)
    if user is None or user.status != "active" or user.auth_version != auth_version:
        return False
    return True


__all__ = [
    "UserError",
    "UsernameConflict",
    "UserNotFound",
    "InvalidInput",
    "AuthFailed",
    "Forbidden",
    "NoAdminLeft",
    "normalize_username",
    "authenticate",
    "init_first_admin",
    "list_users",
    "create_user",
    "set_status",
    "reset_password",
    "change_password",
    "is_active",
    "ROLES",
    "STATUSES",
]
