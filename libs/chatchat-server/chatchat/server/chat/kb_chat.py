from __future__ import annotations

import asyncio, json
import uuid
from typing import AsyncIterable, List, Optional, Literal

from fastapi import Body, Depends, HTTPException, Request, status
from fastapi.concurrency import run_in_threadpool
from sse_starlette.sse import EventSourceResponse
from langchain.callbacks import AsyncIteratorCallbackHandler
from langchain.prompts.chat import ChatPromptTemplate


from chatchat.settings import Settings
from chatchat.server.auth.deps import require_password_changed
from chatchat.server.db.models.user_model import UserModel
from chatchat.server.db.session import get_db
from chatchat.server.db.repository import (
    add_message,
    create_conversation,
    get_owned_conversation,
    update_message,
)
from chatchat.server.knowledge_base.temp_files import assert_temp_owner
from chatchat.server.memory import memory_service
from sqlalchemy.orm import Session
from chatchat.server.agent.tools_factory.search_internet import search_engine
from chatchat.server.api_server.api_schemas import OpenAIChatOutput
from chatchat.server.chat.utils import History
from chatchat.server.knowledge_base.kb_service.base import KBServiceFactory
from chatchat.server.knowledge_base.kb_doc_api import search_docs, search_temp_docs
from chatchat.server.knowledge_base.utils import format_reference
from chatchat.server.utils import (wrap_done, get_ChatOpenAI, get_default_llm,
                                   BaseResponse, get_prompt_template, build_logger,
                                   check_embed_model, api_address
                                )


logger = build_logger()


async def kb_chat(query: str = Body(..., description="用户输入", examples=["你好"]),
                mode: Literal["local_kb", "temp_kb", "search_engine"] = Body("local_kb", description="知识来源"),
                kb_name: str = Body("", description="mode=local_kb时为知识库名称；temp_kb时为临时知识库ID，search_engine时为搜索引擎名称", examples=["samples"]),
                top_k: int = Body(Settings.kb_settings.VECTOR_SEARCH_TOP_K, description="匹配向量数"),
                score_threshold: float = Body(
                    Settings.kb_settings.SCORE_THRESHOLD,
                    description="知识库匹配相关度阈值，取值范围在0-1之间，SCORE越小，相关度越高，取到1相当于不筛选，建议设置在0.5左右",
                    ge=0,
                    le=2,
                ),
                history: List[History] = Body(
                    [],
                    description="历史对话",
                    examples=[[
                        {"role": "user",
                        "content": "我们来玩成语接龙，我先来，生龙活虎"},
                        {"role": "assistant",
                        "content": "虎头虎脑"}]]
                ),
                stream: bool = Body(True, description="流式输出"),
                model: str = Body(get_default_llm(), description="LLM 模型名称。"),
                temperature: float = Body(Settings.model_settings.TEMPERATURE, description="LLM 采样温度", ge=0.0, le=2.0),
                max_tokens: Optional[int] = Body(
                    Settings.model_settings.MAX_TOKENS,
                    description="限制LLM生成Token数量，默认None代表模型最大值"
                ),
                prompt_name: str = Body(
                    "default",
                    description="使用的prompt模板名称(在prompt_settings.yaml中配置)"
                ),
                return_direct: bool = Body(False, description="直接返回检索结果，不送入 LLM"),
                conversation_id: Optional[str] = Body(None, description="当前用户会话 ID"),
                request: Request = None,
                user: UserModel = Depends(require_password_changed),
                session: Session = Depends(get_db),
                ):
    if mode == "local_kb":
        kb = KBServiceFactory.get_service_by_name(kb_name)
        if kb is None:
            return BaseResponse(code=404, msg=f"未找到知识库 {kb_name}")
    elif mode == "temp_kb":
        assert_temp_owner(user, kb_name)

    if conversation_id:
        if get_owned_conversation(session, conversation_id, user.id) is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="会话不存在或无权访问",
            )
    else:
        conversation_id = create_conversation(
            session,
            owner_id=user.id,
            chat_type="kb_chat",
            name=(query or "")[:50],
        )
    message_id = add_message(
        session=session,
        conversation_id=conversation_id,
        owner_id=user.id,
        chat_type="kb_chat",
        query=query,
    )

    async def knowledge_base_chat_iterator() -> AsyncIterable[str]:
        try:
            nonlocal history, prompt_name, max_tokens

            history = [History.from_data(h) for h in history]

            # 自动记忆提取：在本轮构造记忆上下文前，把用户明确表达
            # （如“请记住...”）写入长期记忆。失败不阻断正常回答。
            try:
                memory_service.auto_extract(
                    session,
                    user.id,
                    query,
                    source_conversation_id=conversation_id,
                    source_message_id=message_id,
                )
            except Exception:
                pass

            # 会话摘要：历史超过阈值时增量压缩较早内容（默认基于规则，
            # 不依赖模型），记录覆盖位置。失败不阻断正常回答。
            try:
                if conversation_id:
                    memory_service.summarize_conversation(session, user.id, conversation_id)
            except Exception:
                pass

            if mode == "local_kb":
                kb = KBServiceFactory.get_service_by_name(kb_name)
                ok, msg = kb.check_embed_model()
                if not ok:
                    raise ValueError(msg)
                docs = await run_in_threadpool(search_docs,
                                                query=query,
                                                knowledge_base_name=kb_name,
                                                top_k=top_k,
                                                score_threshold=score_threshold,
                                                file_name="",
                                                metadata={})
                source_documents = format_reference(kb_name, docs, api_address(is_public=True))
            elif mode == "temp_kb":
                ok, msg = check_embed_model()
                if not ok:
                    raise ValueError(msg)
                docs = await run_in_threadpool(search_temp_docs,
                                                kb_name,
                                                query=query,
                                                top_k=top_k,
                                                score_threshold=score_threshold,
                                                user=user)
                source_documents = format_reference(kb_name, docs, api_address(is_public=True))
            elif mode == "search_engine":
                result = await run_in_threadpool(search_engine, query, top_k, kb_name)
                docs = [x.dict() for x in result.get("docs", [])]
                source_documents = [f"""出处 [{i + 1}] [{d['metadata']['filename']}]({d['metadata']['source']}) \n\n{d['page_content']}\n\n""" for i,d in enumerate(docs)]
            else:
                docs = []
                source_documents = []
            # import rich
            # rich.print(dict(
            #     mode=mode,
            #     query=query,
            #     knowledge_base_name=kb_name,
            #     top_k=top_k,
            #     score_threshold=score_threshold,
            # ))
            # rich.print(docs)
            if return_direct:
                update_message(
                    session=session,
                    message_id=message_id,
                    owner_id=user.id,
                    response="",
                    metadata={"docs": source_documents},
                )
                yield OpenAIChatOutput(
                    id=f"chat{uuid.uuid4()}",
                    model=None,
                    object="chat.completion",
                    content="",
                    role="assistant",
                    finish_reason="stop",
                    docs=source_documents,
                    message_id=message_id,
                    conversation_id=conversation_id,
                ) .model_dump_json()
                return

            callback = AsyncIteratorCallbackHandler()
            callbacks = [callback]

            # Enable langchain-chatchat to support langfuse
            import os
            langfuse_secret_key = os.environ.get('LANGFUSE_SECRET_KEY')
            langfuse_public_key = os.environ.get('LANGFUSE_PUBLIC_KEY')
            langfuse_host = os.environ.get('LANGFUSE_HOST')
            if langfuse_secret_key and langfuse_public_key and langfuse_host :
                from langfuse import Langfuse
                from langfuse.callback import CallbackHandler
                langfuse_handler = CallbackHandler()
                callbacks.append(langfuse_handler)

            if max_tokens in [None, 0]:
                max_tokens = Settings.model_settings.MAX_TOKENS

            llm = get_ChatOpenAI(
                model_name=model,
                temperature=temperature,
                max_tokens=max_tokens,
                callbacks=callbacks,
            )
            # TODO： 视情况使用 API
            # # 加入reranker
            # if Settings.kb_settings.USE_RERANKER:
            #     reranker_model_path = get_model_path(Settings.kb_settings.RERANKER_MODEL)
            #     reranker_model = LangchainReranker(top_n=top_k,
            #                                     device=embedding_device(),
            #                                     max_length=Settings.kb_settings.RERANKER_MAX_LENGTH,
            #                                     model_name_or_path=reranker_model_path
            #                                     )
            #     print("-------------before rerank-----------------")
            #     print(docs)
            #     docs = reranker_model.compress_documents(documents=docs,
            #                                              query=query)
            #     print("------------after rerank------------------")
            #     print(docs)
            context = "\n\n".join([doc["page_content"] for doc in docs])

            if len(docs) == 0:  # 如果没有找到相关文档，使用empty模板
                prompt_name = "empty"
            prompt_template = get_prompt_template("rag", prompt_name)
            input_msg = History(role="user", content=prompt_template).to_msg_template(False)
            # 用户记忆注入：与普通聊天同一套记忆（长期记忆 + 较早内容摘要），
            # 作为独立系统消息置于 RAG 输入之前（当前用户本轮表达优先）。
            # 失败/无记忆时为空，不改变原行为，也不阻断正常回答。
            _mem_msgs = [
                History(role=m["role"], content=m["content"]).to_msg_template(False)
                for m in memory_service.memory_system_messages(
                    session, user.id, query, conversation_id
                )
            ]
            chat_prompt = ChatPromptTemplate.from_messages(
                _mem_msgs + [i.to_msg_template() for i in history] + [input_msg])

            chain = chat_prompt | llm

            # Begin a task that runs in the background.
            task = asyncio.create_task(wrap_done(
                chain.ainvoke({"context": context, "question": query}),
                callback.done),
            )

            if len(source_documents) == 0:  # 没有找到相关文档
                source_documents.append(f"<span style='color:red'>未找到相关文档,该回答为大模型自身能力解答！</span>")

            if stream:
                answer = ""
                # yield documents first
                ret = OpenAIChatOutput(
                    id=f"chat{uuid.uuid4()}",
                    object="chat.completion.chunk",
                    content="",
                    role="assistant",
                    model=model,
                    docs=source_documents,
                    message_id=message_id,
                    conversation_id=conversation_id,
                )
                yield ret.model_dump_json()

                async for token in callback.aiter():
                    answer += token
                    ret = OpenAIChatOutput(
                        id=f"chat{uuid.uuid4()}",
                        object="chat.completion.chunk",
                        content=token,
                        role="assistant",
                        model=model,
                        message_id=message_id,
                        conversation_id=conversation_id,
                    )
                    yield ret.model_dump_json()
            else:
                answer = ""
                async for token in callback.aiter():
                    answer += token
                ret = OpenAIChatOutput(
                    id=f"chat{uuid.uuid4()}",
                    object="chat.completion",
                    content=answer,
                    role="assistant",
                    model=model,
                    message_id=message_id,
                    conversation_id=conversation_id,
                )
                yield ret.model_dump_json()
            await task
            update_message(
                session=session,
                message_id=message_id,
                owner_id=user.id,
                response=answer,
                metadata={"docs": source_documents},
            )
        except asyncio.exceptions.CancelledError:
            logger.warning("streaming progress has been interrupted by user.")
            return
        except Exception as e:
            logger.error(f"error in knowledge chat: {e}")
            yield {"data": json.dumps({"error": str(e)})}
            return

    if stream:
        return EventSourceResponse(knowledge_base_chat_iterator())
    else:
        return await knowledge_base_chat_iterator().__anext__()
