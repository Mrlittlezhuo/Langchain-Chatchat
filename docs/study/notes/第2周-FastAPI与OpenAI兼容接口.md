# 第 2 周：FastAPI 与 OpenAI 兼容接口

## 1. 本周结论

本周已经完成，学习时间截止到 `2026-08-28`。

本周的重点不是 Agent 怎样选择工具，而是先弄清一个模型请求怎样穿过 FastAPI：

1. FastAPI 应用怎样注册 Router；
2. 为什么项目中同时存在 `/chat/chat/completions` 和 `/v1/chat/completions`；
3. `/v1/chat/completions` 怎样选择模型平台并创建 OpenAI 客户端；
4. 非流式请求和 SSE 流式请求的代码分支有什么不同；
5. `async def`、`await`、`async with`、`yield` 和事件循环在这条调用链中分别解决什么问题；
6. 客户端中断流式连接后，项目如何感知并结束转发。

本周手工验证通过的内容：

- FastAPI Swagger 和 OpenAPI 文档可用；
- `/v1/chat/completions` 非流式请求成功；
- `/v1/chat/completions` SSE 流式请求成功；
- 客户端中断 SSE 后，服务端进入 `CancelledError` 处理；
- 可以从 `model_settings.yaml` 一直追踪到 Ollama 的 `base_url` 和异步客户端；
- 可以解释 Semaphore 为什么要在请求前获取、请求后释放。

---

## 2. 阅读边界与源码版本

本文中的行号对应当前学习快照：

- Langchain-Chatchat：`0.3.1.3`；
- LangChain：`0.1.17`；
- Python：`3.10.20`；
- 模型服务：Ollama；
- LLM：`qwen2:7b`；
- Embedding：`bge-m3`；
- API：`http://127.0.0.1:7861`；
- Ollama：`http://127.0.0.1:11434`。

下文源码路径均相对于：

```text
/home/lab239/chenzhuo/Langchain-Chatchat/libs/chatchat-server
```

---

## 3. FastAPI 应用是怎样组装的

### 3.1 应用入口

源码位置：

```text
chatchat/server/api_server/server_app.py:23-63
```

关键代码对应关系：

- `server_app.py:23` 定义 `create_app()`；
- `server_app.py:24` 创建 FastAPI 对象；
- `server_app.py:29-36` 根据配置决定是否添加 CORS 中间件；
- `server_app.py:38-40` 把根路径 `/` 重定向到 `/docs`；
- `server_app.py:42-47` 把各个 Router 注册到同一个 FastAPI 应用；
- `server_app.py:57` 挂载 `/media` 静态文件；
- `server_app.py:61` 挂载 `/img` 静态文件；
- `server_app.py:63` 返回已组装好的 `app`。

这里可以把 FastAPI 应用理解为一个“总路由器”，它本身不需要把所有业务代码都写在一个文件里，而是将各个功能分组后通过 `include_router()` 组合起来。

### 3.2 Router 分组

`server_app.py:42-47` 注册了六组 Router：

| Router | 主要职责 | 常见前缀 |
|---|---|---|
| `chat_router` | 项目自身的对话、知识库、Agent 编排 | `/chat` |
| `kb_router` | 知识库管理 | `/knowledge_base` |
| `tool_router` | 工具列表和直接调用 | `/tools` |
| `openai_router` | OpenAI 兼容模型网关 | `/v1` |
| `server_router` | 服务状态 | `/server` |
| `mcp_router` | MCP 连接管理 | `/api/v1/mcp_connections` |

“Router 前缀 + 方法路径”才是最终 HTTP 路径。

例如：

```python
openai_router = APIRouter(prefix="/v1")

@openai_router.post("/chat/completions")
```

最终路径是：

```text
POST /v1/chat/completions
```

---

## 4. 为什么有两个 `chat/completions`

项目中存在两条很像的路径：

```text
POST /chat/chat/completions
POST /v1/chat/completions
```

它们都采用 OpenAI 风格的请求和响应，但定位不同。

### 4.1 `/chat/chat/completions`：项目业务编排接口

源码位置：

```text
chatchat/server/api_server/chat_routes.py:28
chatchat/server/api_server/chat_routes.py:45-49
```

- `chat_routes.py:28` 设置 Router 前缀 `/chat`；
- `chat_routes.py:45` 设置方法路径 `/chat/completions`；
- 两者合并为 `/chat/chat/completions`。

这条路径不只负责“转发模型请求”，还处理：

- `conversation_id`；
- 消息入库；
- 工具配置；
- Agent 对话；
- MCP；
- 项目自定义状态事件。

因此，它是 Langchain-Chatchat 自身的业务入口。

### 4.2 `/v1/chat/completions`：模型平台兼容网关

源码位置：

```text
chatchat/server/api_server/openai_routes.py:30
chatchat/server/api_server/openai_routes.py:147-153
```

- `openai_routes.py:30` 设置 Router 前缀 `/v1`；
- `openai_routes.py:147` 设置方法路径 `/chat/completions`；
- 两者合并为 `/v1/chat/completions`。

它的主要职责是：

1. 根据模型名找到配置平台；
2. 构造 OpenAI 客户端；
3. 把请求转发到 Ollama、Xinference 或其他 OpenAI 兼容服务；
4. 以 OpenAI 格式返回完整响应或流式分块。

因此，它更像项目内部的“模型网关”。

### 4.3 WebUI 实际调用哪个

源码位置：

```text
chatchat/webui_pages/dialogue/dialogue.py:394
chatchat/webui_pages/dialogue/dialogue.py:413-437
```

`dialogue.py:394` 创建客户端时使用：

```python
base_url=f"{api_address()}/chat"
```

`dialogue.py:437` 又调用：

```python
client.chat.completions.create(**params)
```

OpenAI SDK 会在 `base_url` 后面追加 `/chat/completions`，因此 WebUI 普通对话实际访问：

```text
/chat + /chat/completions
= /chat/chat/completions
```

所以 `/v1/chat/completions` 不是只给 Codex 使用，它是给任何支持 OpenAI API 协议的客户端使用；而当前 WebUI 普通对话走的是项目业务入口。

---

## 5. `/v1/chat/completions` 完整调用链

本周实际追踪的链路是：

```text
HTTP POST /v1/chat/completions
    ↓
FastAPI + OpenAIChatInput 解析和校验请求
    ↓
create_chat_completions()
    ↓
get_model_client(body.model)
    ↓
get_model_info() / get_config_models()
    ↓
选择模型平台 + 获取 Semaphore
    ↓
get_OpenAIClient(..., is_async=True)
    ↓
openai.AsyncClient(base_url, api_key)
    ↓
openai_request(client.chat.completions.create, body)
    ↓
Ollama OpenAI 兼容端点 /v1/chat/completions
    ↓
非流式 JSON 或流式 SSE
    ↓
FastAPI 返回调用方
```

这条链的三层职责可以概括为：

| 层 | 职责 |
|---|---|
| HTTP 路由层 | 接收请求、参数校验、选择处理函数 |
| 模型调度层 | 找到平台、控制并发、创建客户端 |
| 响应适配层 | 区分非流式和流式，转换并转发响应 |

---

## 6. 请求参数是怎样被解析的

源码位置：

```text
chatchat/server/api_server/api_schemas.py:21-53
```

`OpenAIChatInput` 继承 `OpenAIBaseInput`。关键字段包括：

- `messages`：对话消息列表；
- `model`：模型名称；
- `stream`：是否流式返回；
- `temperature`：采样温度；
- `max_tokens`：最大生成 token 数；
- `tools` 和 `tool_choice`：OpenAI 风格的工具定义与选择；
- `extra_body`：通过 alias 映射到 `extra_json`；
- `Config.extra = "allow"`：允许额外字段。

FastAPI 在调用路由函数之前，会把 JSON 解析为 `OpenAIChatInput` 对象。所以路由函数拿到的 `body` 不是普通字典，而是经过 Pydantic 校验的模型对象。

`openai_routes.py:108` 使用：

```python
params = body.model_dump(exclude_unset=True)
```

它的含义是：

1. `model_dump()` 把 Pydantic 模型转换为 Python 字典；
2. `exclude_unset=True` 只保留调用者显式传入的参数；
3. 转换后的 `params` 可以通过 `method(**params)` 传给 OpenAI SDK。

---

## 7. 模型配置如何变成客户端

### 7.1 读取平台配置

源码位置：

```text
chatchat/server/utils.py:59-64
```

```python
platforms = [m.model_dump() for m in Settings.model_settings.MODEL_PLATFORMS]
return {m["platform_name"]: m for m in platforms}
```

这两行完成两次转换：

1. 把 `MODEL_PLATFORMS` 中每个 Pydantic 平台对象转成字典；
2. 把字典列表重组为以 `platform_name` 为 key 的字典。

例如：

```python
{
    "ollama": {
        "platform_name": "ollama",
        "api_base_url": "http://127.0.0.1:11434/v1",
        "api_key": "EMPTY",
        ...
    }
}
```

### 7.2 根据模型名查找平台

源码位置：

```text
chatchat/server/utils.py:114-198
```

`get_config_models()` 的主要步骤：

1. `utils.py:134-146` 决定要查找哪些模型类型；
2. `utils.py:148` 遍历模型平台；
3. `utils.py:152-161` 如果启用自动检测，则向 Xinference 查询模型；
4. `utils.py:163-170` 遍历各类模型列表；
5. `utils.py:171-180` 按模型名匹配并组织调用信息；
6. `utils.py:184-198` 由 `get_model_info()` 决定返回第一个还是所有匹配项。

当前 `qwen2:7b` 匹配到 Ollama，关键调用信息是：

```text
platform_name = ollama
api_base_url = http://127.0.0.1:11434/v1
api_key = EMPTY
```

### 7.3 创建 OpenAI 客户端

源码位置：

```text
chatchat/server/utils.py:414-451
```

`get_OpenAIClient()` 的输入可以是 `platform_name` 或 `model_name`。它最终组织出：

```python
params = {
    "base_url": platform_info.get("api_base_url"),
    "api_key": platform_info.get("api_key"),
}
```

如果配置了 `api_proxy`，`utils.py:438-442` 还会为 HTTP 请求增加网络代理。这里的代理是 HTTP 网络代理，用于客户端访问外部模型 API，与 Python 代理对象无关。

`utils.py:444-451` 根据 `is_async` 返回不同客户端：

```text
is_async=True  -> openai.AsyncClient
is_async=False -> openai.Client
```

本周的 `/v1/chat/completions` 调用链使用 `is_async=True`，所以返回异步客户端。

---

## 8. Semaphore 在这里做什么

源码位置：

```text
chatchat/server/api_server/openai_routes.py:26-63
```

### 8.1 key 的含义

```python
key = (m, c["platform_name"])
```

`key` 是一个二元组：

```text
(模型名, 平台名)
```

例如：

```python
("qwen2:7b", "ollama")
```

它用来区分每个“模型 + 平台”组合的并发限制。

### 8.2 Semaphore 的含义

```python
model_semaphores[key] = asyncio.Semaphore(api_concurrencies)
```

Semaphore 可以理解为一组“并发许可证”。

假设 `api_concurrencies=5`：

- 初始有 5 个许可；
- 请求进入时，`await semaphore.acquire()` 获取 1 个；
- 已经有 5 个请求占用时，新请求在 `acquire()` 处异步等待；
- 请求完成或异常时，`finally` 中的 `release()` 归还 1 个；
- 之前等待的请求就可以继续执行。

`finally` 很重要，因为即使模型请求报错，也必须归还许可，否则最终所有新请求都会被永久阻塞。

### 8.3 本周发现的实现细节

`openai_routes.py:45` 尝试从模型信息中读取 `api_concurrencies`：

```python
api_concurrencies = c.get("api_concurrencies", DEFAULT_API_CONCURRENCIES)
```

但当前 `get_config_models()` 在 `server/utils.py:172-180` 组织返回字典时，没有携带 `api_concurrencies`。因此这条路径当前会回退到 `DEFAULT_API_CONCURRENCIES=5`。

该细节本周已知晓，不影响继续学习，也未写入项目缺陷清单。

---

## 9. 这条链路中的异步概念

### 9.1 `async def`

```python
async def get_model_client(...):
```

`async def` 定义的是协程函数。调用它时不会像普通函数一样直接得到最终结果，而是得到一个可由事件循环调度的对象。

但“写了 `async def`”不等于函数内的任意代码都自动非阻塞。如果函数内直接做长时间 CPU 计算，且没有线程或进程卸载，仍然会占住当前事件循环线程。

### 9.2 `await`

```python
result = await method(**params)
```

`await` 有两层含义：

1. 当前协程要等待这个异步操作的结果；
2. 当底层正在等待网络 I/O 时，当前协程可以把执行权交还事件循环，让它调度其他已就绪任务。

请求模型之所以适合异步，是因为大部分时间是在等待 socket 返回数据，而不是 Python 线程一直在执行计算。

### 9.3 事件循环

事件循环是协程调度器。它的工作可以简化为：

```text
运行任务 A
    ↓
A await 网络 I/O，暂时不可继续
    ↓
事件循环改为运行任务 B
    ↓
A 的 socket 数据到达
    ↓
事件循环再恢复 A
```

这是“并发”，不一定是两段 Python 代码在一个 CPU 核上同一时刻执行。

### 9.4 `@asynccontextmanager`、`async with` 和 `yield`

源码位置：

```text
chatchat/server/api_server/openai_routes.py:33-63
chatchat/server/api_server/openai_routes.py:151-153
```

`get_model_client()` 函数内部有 `yield`，并且被 `@asynccontextmanager` 装饰，所以它可以配合 `async with` 管理资源的获取和释放。

```python
async with get_model_client(body.model) as client:
    result = await openai_request(...)
```

执行顺序不是“调用完 `get_model_client()` 就结束”，而是：

```text
1. 执行 get_model_client() 中 yield 之前的代码
2. await semaphore.acquire() 获取许可
3. yield AsyncClient，并在这里暂停 get_model_client()
4. yield 的客户端被赋值给 as client
5. 执行 async with 代码块内的模型请求
6. 代码块结束，恢复 get_model_client()
7. 执行 finally 中的 semaphore.release()
```

所以 `yield` 后面完全可以有代码。它何时继续，取决于外部何时离开 `async with` 代码块。

---

## 10. 非流式请求链路

源码位置：

```text
chatchat/server/api_server/openai_routes.py:108-118
```

当 `stream=false` 时，条件走到 `openai_routes.py:114-118`：

```python
result = await method(**params)
return result.model_dump()
```

其中：

- `method` 是 `client.chat.completions.create`；
- `params` 是从 `OpenAIChatInput` 转换出的字典；
- `await method(**params)` 才是向 Ollama 发起真实模型请求的位置；
- 这个 `await` 会一直等到完整响应返回；
- `result.model_dump()` 把 OpenAI 响应对象转换为 FastAPI 可以序列化的字典。

### 10.1 手工验证

请求：

```json
{
  "model": "qwen2:7b",
  "messages": [
    {
      "role": "user",
      "content": "请只回答：非流式接口运行正常"
    }
  ],
  "stream": false
}
```

验证结果：

| 字段 | 实际值 | 含义 |
|---|---|---|
| `object` | `chat.completion` | 完整聊天响应 |
| `model` | `qwen2:7b` | 实际调用模型 |
| `choices[0].message.content` | `非流式接口运行正常。` | 模型最终文本 |
| `finish_reason` | `stop` | 模型正常结束 |
| `usage.prompt_tokens` | `29` | 输入 token 数 |
| `usage.completion_tokens` | `8` | 输出 token 数 |
| `usage.total_tokens` | `37` | 总 token 数 |
| `system_fingerprint` | `fp_ollama` | 响应来自 Ollama 兼容层 |

结论：从 Langchain-Chatchat `/v1` 网关到 Ollama `qwen2:7b` 的非流式调用链已跑通。

---

## 11. SSE 流式请求链路

源码位置：

```text
chatchat/server/api_server/openai_routes.py:73-113
```

当 `stream=true` 时，`openai_routes.py:112-113` 返回：

```python
EventSourceResponse(generator())
```

`EventSourceResponse` 建立 SSE 响应，`generator()` 负责不断提供下一个事件。

真正读取上游模型分块的是 `openai_routes.py:86-89`：

```python
async for chunk in await method(**params):
    yield chunk.model_dump_json()
```

它的运行方式是：

```text
Ollama 产生一个 chunk
    ↓
OpenAI AsyncClient 解析这个 chunk
    ↓
async for 取到 chunk
    ↓
model_dump_json() 转换为 JSON
    ↓
yield 给 EventSourceResponse
    ↓
SSE 把 data: ... 发送给客户端
    ↓
等待下一个 chunk
```

这不是等模型生成完整答案后再切开，而是上游模型返回一块，项目就尽快向下游转发一块。

### 11.1 实际事件序列

本周用问题“请用一句不超过20个字的话解释什么是流式输出”进行流式请求。

观察到的序列可简化为：

```text
第一帧：role=assistant，content 为首个文本片段
中间帧：content 持续增加，finish_reason=null
最后帧：content=null，finish_reason=stop
连接结束
```

多个 `content` 片段组合后得到完整回答：

```text
流式输出是指数据或信息实时传输并在到达时进行处理的输出方式。
```

每一帧的 `object` 是：

```text
chat.completion.chunk
```

这与非流式响应的 `chat.completion` 不同。

本次实验没有看到单独的 `data: [DONE]`，而是最后一个 `finish_reason=stop` 的 chunk 后关闭连接。这一点先记为兼容性观察，尚未归类为项目缺陷。

---

## 12. 客户端中断时发生了什么

源码位置：

```text
chatchat/server/api_server/openai_routes.py:101-103
```

当客户端在流式请求期间断开连接时，`EventSourceResponse` 会取消正在运行的生成器任务。项目捕获：

```python
except asyncio.exceptions.CancelledError:
    logger.warning("streaming progress has been interrupted by user.")
    return
```

手工中断 `curl` 后，服务端实际输出：

```text
WARNING | chatchat.server.api_server.openai_routes:generator:102 
- streaming progress has been interrupted by user
```

这证明：

1. 客户端断开已传递到 FastAPI/SSE 生成器；
2. Langchain-Chatchat 已停止继续读取和转发当前流；
3. 该取消被单独处理，没有被当成普通 500 异常。

需要严格区分：这个日志只能证明 Langchain-Chatchat 的转发协程被取消；它本身不足以证明 Ollama GPU 上的生成在同一瞬间完全停止。

---

## 13. 不存在模型的错误实验

本周还发送了：

```json
{
  "model": "model-does-not-exist",
  "messages": [{"role": "user", "content": "你好"}],
  "stream": false
}
```

实际结果：

```text
Internal Server Error
HTTP 状态码：500
```

该请求的失败位置可以从源码确定：

1. JSON 可以通过 `OpenAIChatInput` 结构校验；
2. `get_model_info(model_name=..., multiple=True)` 返回空字典；
3. `openai_routes.py:41` 的 `assert model_infos` 失败；
4. 还没有执行到 `yield get_OpenAIClient(...)`；
5. 因此请求没有到达 Ollama。

结论：这是 Langchain-Chatchat 模型配置查找阶段的错误，不是 Ollama 模型推理错误。

从 API 设计角度看，不存在模型更适合返回结构化的 `400` 或 `404`，而不是由 `assert` 转成通用 `500`。这是一个待决定是否纳入优化清单的候选项，本文不自动写入《项目缺陷与优化清单》。

---

## 14. OpenAI 兼容接口的工程价值

OpenAI 兼容不代表底层一定是 OpenAI 模型，而是“对外提供相同风格的协议”。

当前链路是：

```text
调用方使用 OpenAI SDK
    ↓
Langchain-Chatchat /v1/chat/completions
    ↓
OpenAI AsyncClient
    ↓
Ollama OpenAI-compatible API
    ↓
qwen2:7b
```

这种设计的优点：

- 上层业务不需要针对每个模型平台重写 SDK 调用；
- 可以通过更换 `base_url`、`api_key` 和模型名切换平台；
- 通用 OpenAI 客户端、测试工具和第三方应用更容易接入；
- 流式响应、token 用量和错误格式可以向同一协议收敛。

---

## 15. 自动化测试尝试与准确结论

测试文件：

```text
tests/api/test_openai_wrap.py:1-30
```

用例的意图：

- `test_openai_wrap.py:11-15` 用 `api_address() + /v1` 创建同步 OpenAI 客户端；
- `test_openai_wrap.py:18-24` 真实请求 `/v1/chat/completions`；
- `test_openai_wrap.py:27-30` 真实请求 `/v1/embeddings`。

已安装 `pytest 7.4.4`，但执行用例时出现两层环境问题：

1. `pyproject.toml` 默认 `addopts` 包含 `--snapshot-warn-unused`，当前未安装提供该参数的 Syrupy 插件；
2. 使用 `-o addopts=''` 绕开插件参数后，测试进程没有加载当前 `CHATCHAT_ROOT`，导致测试进程选到默认模型名，与正在运行的 API 服务配置不一致。

因此本周对测试结果的准确记录是：

```text
手工接口验证：通过
自动化 pytest：因测试进程配置不一致而暂缓
```

为了学习进度，本周按核心功能已手工验证通过处理；但不会在文档中虚假记录为“pytest 已通过”。

---

## 16. 本周验收答案

### 问题 1：一个 `/v1/chat/completions` 请求从哪里进入？

从 `server_app.py:45` 注册的 `openai_router` 进入；Router 前缀在 `openai_routes.py:30` 是 `/v1`，方法路径在 `openai_routes.py:147` 是 `/chat/completions`。

### 问题 2：为什么有两个相似的接口？

`/chat/chat/completions` 是 Langchain-Chatchat 业务编排入口，处理会话、Agent、工具和 MCP；`/v1/chat/completions` 是 OpenAI 兼容模型网关，主要处理模型平台选择和请求转发。

### 问题 3：模型是怎样被选中的？

`body.model` 传给 `get_model_client()`，然后由 `get_model_info()` 在 `MODEL_PLATFORMS` 中查找包含该模型的平台，最后使用平台的 `api_base_url` 和 `api_key` 构造 OpenAI 客户端。

### 问题 4：非流式与流式最核心的区别是什么？

非流式在 `await method(**params)` 处等待完整响应，然后一次返回字典；流式则返回 `EventSourceResponse(generator())`，生成器通过 `async for` 逐个读取上游 chunk，再逐个 `yield` 给客户端。

### 问题 5：为什么需要 Semaphore？

用于限制每个“模型 + 平台”组合同时占用的请求数，防止无限并发压垮模型服务。

### 问题 6：客户端断开 SSE 后怎样处理？

SSE 任务被取消，生成器捕获 `asyncio.exceptions.CancelledError`，记录 warning 并结束转发。

---

## 17. 面试版总结

可以简洁地表述为：

> 我在 Langchain-Chatchat 中追踪了 FastAPI 路由注册、Pydantic 参数校验、模型平台选择、OpenAI 异步客户端和 SSE 流式转发的完整链路。我使用 qwen2:7b 分别验证了非流式与流式请求，并通过主动中断客户端确认了 `CancelledError` 处理链路。同时我能够解释 `/chat/chat/completions` 业务编排接口与 `/v1/chat/completions` 模型网关接口的区别。

---

## 18. 与后续周次的衔接

本周到达的边界是“HTTP 请求怎样到达模型并流式返回”。

后续周次的分工：

- 第 3 周：文档如何加载、分块、Embedding 并写入 FAISS/SQLite；
- 第 4 周：问题如何经过 FAISS、BM25 和融合检索找到文档；
- 第 6 周：模型如何在 Agent 循环中做出 `Action`，执行工具，接收 `Observation`，再生成 `Finish`。

之前已经提前阅读的 Agent 内容已归档到：

```text
docs/study/notes/第6周-Agent对话完整调用链解析.md
```

从下一步开始，主线回到第 3 周的 RAG 入库流程。
