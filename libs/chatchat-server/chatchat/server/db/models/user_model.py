from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, Integer, String

from chatchat.server.db.base import Base


class UserModel(Base):
    """
    最小用户账户模型。

    物理表使用 user_account，避免保留字 user。password_hash 禁止出现
    在 repr、API 响应或日志中。
    """

    __tablename__ = "user_account"
    __table_args__ = (
        CheckConstraint("role IN ('admin', 'user')", name="ck_user_account_role"),
        CheckConstraint(
            "status IN ('active', 'disabled')",
            name="ck_user_account_status",
        ),
        CheckConstraint(
            "auth_version >= 1",
            name="ck_user_account_auth_version",
        ),
    )

    id = Column(
        String(32),
        primary_key=True,
        comment="用户ID(UUID hex，服务端生成)",
    )
    username = Column(
        String(64),
        unique=True,
        index=True,
        nullable=False,
        comment="用户名（规范化小写，仅存 a-z0-9._-）",
    )
    display_name = Column(
        String(100),
        nullable=False,
        comment="显示名称（允许 Unicode）",
    )
    password_hash = Column(
        String(255),
        nullable=False,
        comment="scrypt 密码哈希（禁止外泄）",
    )
    role = Column(String(16), nullable=False, default="user", comment="admin / user")
    status = Column(
        String(16),
        nullable=False,
        default="active",
        comment="active / disabled",
    )
    must_change_password = Column(
        Boolean, nullable=False, default=True, comment="是否必须修改密码"
    )
    auth_version = Column(Integer, nullable=False, default=1, comment="认证版本")
    create_time = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        comment="创建时间",
    )
    update_time = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow,
        comment="更新时间",
    )

    def __repr__(self):
        # 不含 password_hash / 明文密码
        return (
            f"<User(id={self.id!r}, username={self.username!r}, role={self.role!r}, "
            f"status={self.status!r}, "
            f"must_change_password={self.must_change_password}, "
            f"auth_version={self.auth_version})>"
        )


__all__ = ["UserModel"]
