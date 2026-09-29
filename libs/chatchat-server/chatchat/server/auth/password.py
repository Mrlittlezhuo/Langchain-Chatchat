"""盐化 scrypt 密码哈希与验证（仅标准库，无新增依赖）。

格式（自描述、可版本化，单行可安全存入 VARCHAR(255)）::

    scrypt$1$n=16384,r=8,p=5$<base64url-salt>$<base64url-digest>

参数固定为 N=2^14、r=8、p=5、derived key=64 bytes。
盐使用 CSPRNG 随机 16 字节，每个密码独立。
禁止在 repr/日志/响应中出现明文密码；未知用户名路径执行固定
dummy hash，降低用户名枚举的时序差异。
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import secrets

#: scrypt 固定参数（OWASP 最低等效配置之一）
SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 5
SCRYPT_DKLEN = 64  # derived key 64 bytes

_FORMAT_VERSION = "1"
_PARAMS = f"n={SCRYPT_N},r={SCRYPT_R},p={SCRYPT_P}"

#: 新密码约束：最少 12 字符，UTF-8 后最多 1024 bytes
MIN_PASSWORD_CHARS = 12
MAX_PASSWORD_BYTES = 1024

_DUMMY_PASSWORD = b"chatchat-dummy-password"
_DUMMY_SALT = b"chatchat-dummy!!"
_DUMMY_EXPECTED = bytes(SCRYPT_DKLEN)


def dummy_verify() -> None:
    """执行固定 scrypt 工作量，对齐未知用户名和错误密码路径。"""
    actual = hashlib.scrypt(
        _DUMMY_PASSWORD,
        salt=_DUMMY_SALT,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=SCRYPT_DKLEN,
    )
    hmac.compare_digest(actual, _DUMMY_EXPECTED)


class PasswordValidationError(ValueError):
    """密码不满足长度/编码约束。"""


def validate_password(password: str) -> None:
    """校验新密码的类型、字符数和 UTF-8 字节数。"""
    if not isinstance(password, str):
        raise PasswordValidationError("密码必须为字符串")
    if len(password) < MIN_PASSWORD_CHARS:
        raise PasswordValidationError("密码至少需要 12 个字符")
    try:
        encoded = password.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise PasswordValidationError("密码包含无效 Unicode 字符") from exc
    if len(encoded) > MAX_PASSWORD_BYTES:
        raise PasswordValidationError("密码 UTF-8 字节数超出限制")


def _raw(password: str) -> bytes:
    return password.encode("utf-8")


def _decode_base64url(value: str) -> bytes:
    return base64.b64decode(value, altchars=b"-_", validate=True)


def hash_password(password: str) -> str:
    """将明文密码哈希为 scrypt 自描述字符串。"""
    validate_password(password)
    raw_salt = secrets.token_bytes(16)
    salt_b64 = base64.urlsafe_b64encode(raw_salt)
    digest = hashlib.scrypt(
        _raw(password),
        salt=raw_salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=SCRYPT_DKLEN,
    )
    return (
        f"scrypt${_FORMAT_VERSION}${_PARAMS}$"
        f"{salt_b64.decode()}${base64.urlsafe_b64encode(digest).decode()}"
    )


def verify_password(password: str, stored_hash: str) -> bool:
    """验证密码；格式非法或密码超限安全返回 False。"""
    if not isinstance(password, str) or not isinstance(stored_hash, str):
        dummy_verify()
        return False
    try:
        raw_password = _raw(password)
    except UnicodeEncodeError:
        dummy_verify()
        return False
    if len(raw_password) > MAX_PASSWORD_BYTES:
        dummy_verify()
        return False
    try:
        prefix, version, params, salt_b64, digest_b64 = stored_hash.split("$")
        if prefix != "scrypt" or version != _FORMAT_VERSION or params != _PARAMS:
            raise ValueError("bad format")
        salt = _decode_base64url(salt_b64)
        expected = _decode_base64url(digest_b64)
        if len(salt) != 16 or len(expected) != SCRYPT_DKLEN:
            raise ValueError("bad salt or digest length")
        actual = hashlib.scrypt(
            raw_password,
            salt=salt,
            n=SCRYPT_N,
            r=SCRYPT_R,
            p=SCRYPT_P,
            dklen=SCRYPT_DKLEN,
        )
    except (ValueError, TypeError, binascii.Error):
        dummy_verify()
        return False
    return hmac.compare_digest(actual, expected)


__all__ = [
    "PasswordValidationError",
    "validate_password",
    "hash_password",
    "verify_password",
    "dummy_verify",
    "SCRYPT_N",
    "SCRYPT_R",
    "SCRYPT_P",
    "SCRYPT_DKLEN",
    "MIN_PASSWORD_CHARS",
    "MAX_PASSWORD_BYTES",
]
