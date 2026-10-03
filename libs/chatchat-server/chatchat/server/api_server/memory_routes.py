"""记忆 API 路由：全部要求登录，且只能操作当前用户自己的记忆。

- 创建只接收业务字段（type/content/importance/source），owner 来自当前用户；
- 列表只返回当前用户记忆，``update_time DESC``；
- 详情/更新/删除同时过滤 ``id + owner_id``；
- 访问不存在或其他用户的记忆统一 404；
- 响应不返回 owner_id。
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from chatchat.server.auth.deps import require_password_changed
from chatchat.server.db.models.user_model import UserModel
from chatchat.server.db.session import get_db
from chatchat.server.db.repository import (
    MemoryNotOwned,
    create_memory,
    delete_memory,
    get_owned_memory,
    list_memories,
    search_memories,
    update_memory,
)


class MemoryCreate(BaseModel):
    type: str = Field("fact", max_length=16, description="记忆类型 preference/fact/goal/important")
    content: str = Field(..., min_length=1, max_length=2000, description="记忆内容")
    source: str = Field("user", max_length=32, description="来源（user/extract 等）")
    importance: int = Field(1, ge=1, le=5, description="重要性 1-5")


class MemoryUpdate(BaseModel):
    type: Optional[str] = Field(None, max_length=16)
    content: Optional[str] = Field(None, min_length=1, max_length=2000)
    source: Optional[str] = Field(None, max_length=32)
    importance: Optional[int] = Field(None, ge=1, le=5)
    enabled: Optional[bool] = Field(None, description="启用/停用")

    def repo_fields(self) -> dict:
        """转换为 ``repository.update_memory`` 的键名（type→mtype）。"""
        fields = {
            k: v for k, v in self.model_dump().items() if v is not None
        }
        if "type" in fields:
            fields["mtype"] = fields.pop("type")
        return fields


class MemoryOut(BaseModel):
    id: str
    memory_key: str
    type: str
    content: str
    source: str
    importance: int
    enabled: bool
    source_conversation_id: Optional[str]
    source_message_id: Optional[str]
    create_time: Optional[object]
    update_time: Optional[object]


def _out(m) -> MemoryOut:
    return MemoryOut(
        id=m.id,
        memory_key=m.memory_key,
        type=m.type,
        content=m.content,
        source=m.source,
        importance=m.importance,
        enabled=m.enabled,
        source_conversation_id=m.source_conversation_id,
        source_message_id=m.source_message_id,
        create_time=m.create_time,
        update_time=m.update_time,
    )


memory_router = APIRouter(prefix="/memories", tags=["Memories"])


@memory_router.post("", summary="创建记忆（owner 来自当前用户）")
def create_my_memory(
    body: MemoryCreate,
    user: UserModel = Depends(require_password_changed),
    session: Session = Depends(get_db),
) -> MemoryOut:
    m = create_memory(
        session,
        owner_id=user.id,
        content=body.content,
        mtype=body.type,
        source=body.source,
        importance=body.importance,
    )
    return _out(m)


@memory_router.get("", summary="当前用户记忆列表（update_time DESC）")
def list_my_memories(
    user: UserModel = Depends(require_password_changed),
    session: Session = Depends(get_db),
) -> List[MemoryOut]:
    return [_out(m) for m in list_memories(session, user.id)]


@memory_router.get(
    "/search", summary="按查询关键字/重要性检索当前用户相关记忆（离线）"
)
def search_my_memories(
    q: str = "",
    limit: int = 5,
    user: UserModel = Depends(require_password_changed),
    session: Session = Depends(get_db),
) -> List[MemoryOut]:
    return [_out(m) for m in search_memories(session, user.id, q, limit=limit)]


@memory_router.get("/auto", summary="查询当前用户自动记忆开关")
def get_auto_memory(
    user: UserModel = Depends(require_password_changed),
) -> dict:
    return {"auto_memory": bool(user.memory_auto_enabled)}


@memory_router.patch("/auto", summary="设置当前用户自动记忆开关")
def set_auto_memory(
    enabled: bool,
    user: UserModel = Depends(require_password_changed),
    session: Session = Depends(get_db),
) -> dict:
    user.memory_auto_enabled = bool(enabled)
    session.commit()
    session.refresh(user)
    return {"auto_memory": bool(user.memory_auto_enabled)}


@memory_router.get("/{memory_id}", summary="记忆详情")
def get_my_memory(
    memory_id: str,
    user: UserModel = Depends(require_password_changed),
    session: Session = Depends(get_db),
) -> MemoryOut:
    m = get_owned_memory(session, memory_id, user.id)
    if m is None:
        raise HTTPException(status_code=404, detail="记忆不存在或无权访问")
    return _out(m)


@memory_router.patch("/{memory_id}", summary="更新记忆")
def patch_my_memory(
    memory_id: str,
    body: MemoryUpdate,
    user: UserModel = Depends(require_password_changed),
    session: Session = Depends(get_db),
) -> MemoryOut:
    fields = body.repo_fields()
    if not fields:
        raise HTTPException(status_code=400, detail="无更新字段")
    try:
        m = update_memory(session, memory_id, user.id, **fields)
    except MemoryNotOwned:
        raise HTTPException(status_code=404, detail="记忆不存在或无权访问")
    if m is None:
        raise HTTPException(status_code=404, detail="记忆不存在或无权访问")
    return _out(m)


@memory_router.delete("/{memory_id}", summary="删除记忆")
def delete_my_memory(
    memory_id: str,
    user: UserModel = Depends(require_password_changed),
    session: Session = Depends(get_db),
) -> dict:
    try:
        delete_memory(session, memory_id, user.id)
    except MemoryNotOwned:
        raise HTTPException(status_code=404, detail="记忆不存在或无权访问")
    return {"deleted": True, "memory_id": memory_id}


__all__ = ["memory_router"]
