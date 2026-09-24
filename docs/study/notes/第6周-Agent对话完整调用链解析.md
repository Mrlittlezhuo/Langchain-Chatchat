# 第 6 周：Agent 对话完整调用链解析

> 本文以当前仓库 `49165d6a`、Langchain-Chatchat `0.3.1.3`、LangChain `0.1.17` 为准，追踪一次 Agent 对话从 Streamlit WebUI 发起请求，到 FastAPI 接口接收、模型决策、工具执行、Observation 回灌、再次调用模型，最后将结果返回浏览器并写入数据库的完整过程。
>
> 当前学习环境使用 `qwen2:7b` 作为 LLM，模型平台为 Ollama，OpenAI 兼容地址为 `http://127.0.0.1:11434/v1`。

## 1. 本文要解决的问题

本文重点回答以下问题：

1. 浏览器中的问题怎样到达 FastAPI？
2. OpenAI 风格的请求怎样转换成项目内部参数？
3. 项目最终选择的是哪个模型，模型地址来自哪里？
4. 模型怎样知道当前有哪些工具？
5. 模型怎样决定调用哪个工具以及传入什么参数？
6. 工具在哪里真正执行？
7. 工具结果怎样重新交给模型？
8. Agent 为什么能够重复执行“模型 → 工具 → 模型”的循环？
9. `PlatformToolsAction`、`ToolStart`、`ToolEnd`、`Finish` 分别代表什么？
10. 为什么 Agent 在后台运行，而主协程同时读取回调事件？
11. SSE 流式响应与普通非流式响应怎样共用一套执行逻辑？
12. 对话历史和工具调用轨迹怎样保存到数据库？

## 2. 先看最终结论

当前项目的 Agent 主链路可以概括为：

```text
浏览器输入问题
    │
    ▼
Streamlit WebUI
    │ OpenAI Python SDK
    │ POST /chat/chat/completions
    ▼
FastAPI 路由 chat_completions()
    │ 参数校验、额外参数提取、工具配置转换
    ▼
chat()
    │ 创建模型、加载工具、加载历史和 intermediate_steps
    ▼
PlatformToolsRunnable
    │ 后台启动 PlatformToolsAgentExecutor.ainvoke()
    ▼
PlatformToolsAgentExecutor._acall()
    │
    ├── 调用模型，让模型生成 AgentAction 或 AgentFinish
    │
    ├── AgentAction：执行本地工具或 MCP 工具
    │       │
    │       ▼
    │   得到 Observation
    │       │
    │       ▼
    │   写入 intermediate_steps
    │       │
    │       ▼
    │   重新构造 agent_scratchpad，再次调用模型
    │
    └── AgentFinish：退出循环，得到最终回答
            │
            ▼
回调队列产生模型、工具和结束状态
            │
            ▼
chat.py 转换为 OpenAIChatOutput
            │
            ├── stream=true：SSE 分块返回
            └── stream=false：服务端聚合后一次返回
            │
            ▼
Streamlit 根据状态更新页面
            │
            ▼
更新数据库中的回答和 intermediate_steps
```

这条链路中必须区分两套逻辑：

| 逻辑 | 职责 | 关键位置 |
|---|---|---|
| Agent 控制循环 | 决定何时调用模型、何时执行工具、何时结束 | `all_tools_agent.py::_acall()` |
| 状态输出链路 | 把模型和工具执行状态实时发送给客户端 | Callback → `PlatformToolsRunnable.invoke()` → `chat.py` |

`chat.py` 中的 `async for item in chat_iterator` 不是 Agent 决策循环。它是状态事件的消费者；真正的决策循环在 `PlatformToolsAgentExecutor._acall()` 中。

### 2.1 这张总图必须拆成两条并行链

上面的总图为了便于概览画成了一条线，但真实代码不是“Agent 全部运行完，再开始处理回调”。从 `PlatformToolsRunnable.invoke()` 创建后台 Task 开始，下面两条链会同时推进：

```text
主执行链
  AgentExecutor → LLM → AgentAction → Tool → Observation → 下一轮 LLM
                         │              │
                         └────触发 Callback────┐
                                              ▼
状态输出链
  Callback → asyncio.Queue → PlatformTools 状态对象 → OpenAIChatOutput → SSE
```

主执行链决定下一步做什么；状态输出链只把正在发生的事情告诉客户端。后文第 12～16 节先把主执行链讲完，第 17 节再回到同时运行的状态输出链。

### 2.2 用六个数据快照贯穿全文

后文不再把类名孤立地串联，而是持续跟踪以下数据：

| 快照 | 所在边界 | 主要内容 |
|---|---|---|
| S0 | WebUI → HTTP | `messages/model/tools/extra_body` |
| S1 | FastAPI Schema → 路由 | `OpenAIChatInput` 与 `model_extra` |
| S2 | 路由 → `chat()` | `query/tool_config/conversation_id/use_mcp` |
| S3 | `chat()` → Agent 包装器 | 模型、工具、历史、`intermediate_steps` |
| S4 | 一轮 Agent 决策与工具执行 | `AgentAction + Observation` |
| S5 | 后端 → WebUI | 状态块、工具结果与最终回答 |

每次进入下一章，先看上一章交出了哪个快照，再看下一章怎样消费它。

## 3. 参与调用链的主要对象

在阅读详细流程前，先认识几个核心对象。

| 对象 | 所在层 | 主要职责 |
|---|---|---|
| `OpenAIChatInput` | API Schema | 校验 OpenAI 风格请求体，保留项目自定义额外字段 |
| `chat_completions()` | FastAPI 路由 | 提取用户问题、工具、会话 ID 等参数，调用内部 `chat()` |
| `ChatPlatformAI` | 模型适配层 | 将 LangChain 消息转换为 OpenAI 请求，访问 Ollama 等模型平台 |
| `PlatformToolsRunnable` | Agent 包装层 | 创建 Agent Executor，并把后台执行与异步事件流连接起来 |
| `PlatformToolsAgentExecutor` | Agent 控制层 | 实现多轮“模型决策 → 工具执行 → Observation 回灌”循环 |
| `PlatformToolsAgentOutputParser` | 输出解析层 | 将模型输出解析成 `AgentAction` 或 `AgentFinish` |
| `intermediate_steps` | Agent 状态 | 保存已经执行过的 `(AgentAction, Observation)` |
| `AgentExecutorAsyncIteratorCallbackHandler` | 回调层 | 将模型和工具事件写入异步队列 |
| `OpenAIChatOutput` | API 输出层 | 将内部状态转换成 OpenAI 风格 JSON |
| `EventSourceResponse` | HTTP 流式层 | 使用 SSE 将多个状态块逐个返回客户端 |

为了演示数据形状，假设用户的问题是“请使用工具处理这个问题”，选择了一个示例工具 `example_tool`，开启流式响应，会话 ID 为 `conv-001`。`example_tool` 只用于说明，不表示仓库一定注册了这个工具。

```python
# S0：WebUI 准备发出的请求
params = {
    "messages": [
        {"role": "user", "content": "请使用工具处理这个问题"}
    ],
    "model": "qwen2:7b",
    "stream": True,
    "tools": ["example_tool"],
    "extra_body": {
        "conversation_id": "conv-001",
        "chat_model_config": {},
        "metadata": {},
        "use_mcp": False,
    },
}
```

## 4. 阶段一：WebUI 组织并发出请求

### 4.1 WebUI 创建 OpenAI 客户端

源码位置：

```text
chatchat/webui_pages/dialogue/dialogue.py:394
```

关键代码：

```python
client = openai.Client(
    base_url=f"{api_address()}/chat",
    api_key="NONE",
    timeout=100000,
)
```

假设 API 地址为：

```text
http://127.0.0.1:7861
```

那么 OpenAI SDK 的 `base_url` 是：

```text
http://127.0.0.1:7861/chat
```

后面调用：

```python
client.chat.completions.create(...)
```

OpenAI SDK 会在基础地址后拼接 `chat/completions`，最终请求地址是：

```text
POST http://127.0.0.1:7861/chat/chat/completions
```

为什么 WebUI 使用 OpenAI SDK：

- WebUI 不需要为本项目单独实现一套聊天 HTTP 客户端。
- 可以复用 OpenAI SDK 对流式和非流式响应的解析能力。
- FastAPI 对外接口可以保持与 OpenAI `chat.completions.create()` 相似的调用方式。

### 4.2 WebUI 组织标准参数和扩展参数

源码位置：

```text
chatchat/webui_pages/dialogue/dialogue.py:400-433
```

主要参数：

```python
params = {
    "messages": messages,
    "model": llm_model,
    "stream": stream,
    "extra_body": extra_body,
}
```

其中 `extra_body` 包含项目自定义字段：

```python
extra_body = {
    "metadata": files_upload,
    "chat_model_config": chat_model_config,
    "conversation_id": conversation_id,
    "tool_input": tool_input,
    "upload_image": upload_image,
    "use_mcp": use_mcp,
}
```

标准 OpenAI 参数和项目参数被分开组织：

```text
标准参数：messages、model、stream、tools、tool_choice、max_tokens
扩展参数：conversation_id、chat_model_config、metadata、use_mcp 等
```

这样做的作用是：外部仍可使用 OpenAI SDK，但项目可以通过额外字段传递会话、附件和 MCP 等业务状态。

### 4.3 WebUI 发出流式请求

源码位置：

```text
chatchat/webui_pages/dialogue/dialogue.py:435-437
```

```python
for d in client.chat.completions.create(**params):
    ...
```

这里使用普通 `for`，是因为 Streamlit 页面代码使用的是同步 OpenAI Client。底层 HTTP 响应虽然是持续到达的 SSE 数据，但 SDK 已将其包装成同步可迭代对象。

### 4.4 本阶段交接：S0 从 WebUI 进入 FastAPI

本阶段没有调用模型，也没有创建 Agent。它只完成了一件事：把页面状态组织成 S0，并通过 HTTP 发给 `/chat/chat/completions`。下一阶段消费的正是这份 JSON。

```text
S0：OpenAI 风格 HTTP JSON
  → FastAPI 路由匹配
  → OpenAIChatInput 校验
  → S1：Pydantic 对象
```

## 5. 阶段二：FastAPI 找到接口并校验请求

### 5.1 FastAPI 注册聊天路由

源码位置：

```text
chatchat/server/api_server/server_app.py:23-47
```

`create_app()` 创建 FastAPI 应用，并注册：

```python
app.include_router(chat_router)
```

`chat_router` 的统一前缀定义在：

```text
chatchat/server/api_server/chat_routes.py:28
```

```python
chat_router = APIRouter(prefix="/chat", tags=["ChatChat 对话"])
```

接口自身路径定义在：

```text
chatchat/server/api_server/chat_routes.py:45
```

```python
@chat_router.post("/chat/completions")
```

两者合并后得到最终路径：

```text
/chat + /chat/completions
= /chat/chat/completions
```

### 5.2 Pydantic 校验 OpenAI 请求

源码位置：

```text
chatchat/server/api_server/api_schemas.py:21-53
```

接口参数声明为：

```python
body: OpenAIChatInput
```

`OpenAIChatInput` 定义了：

```python
messages
model
max_tokens
stream
temperature
tools
tool_choice
```

这些字段使用 OpenAI Python SDK 提供的消息和工具类型注解，因此 FastAPI/Pydantic 可以在进入业务代码前完成结构校验。

### 5.3 为什么额外字段不会被丢弃

`OpenAIBaseInput` 中设置：

```python
class Config:
    extra = "allow"
```

这意味着请求中没有显式声明的字段，例如：

```text
conversation_id
chat_model_config
metadata
use_mcp
```

仍会保留在 `body.model_extra` 中。

这是 OpenAI 兼容接口与项目自定义能力能够同时存在的关键。

### 5.4 本阶段交接：S1 已经是 Python 对象

到这里，外部 JSON 已经变成 `OpenAIChatInput`。标准字段保存在 `body.messages/body.tools` 等属性中，Chatchat 扩展字段保存在 `body.model_extra`。下一阶段不再处理原始 HTTP 字节，而是从 S1 提取内部业务参数。

```text
S1：OpenAIChatInput
  → chat_completions() 提取 query、工具和扩展字段
  → S2：chat() 的函数参数
```

## 6. 阶段三：路由层转换参数

源码位置：

```text
chatchat/server/api_server/chat_routes.py:45-125
```

### 6.1 补充 `max_tokens`

```python
if body.max_tokens in [None, 0]:
    body.max_tokens = Settings.model_settings.MAX_TOKENS
```

作用：请求没有指定最大输出长度时，使用项目配置。

### 6.2 取出项目扩展字段

```python
extra = {**body.model_extra} or {}
for key in list(extra):
    delattr(body, key)
```

转换后可以通过：

```python
extra.get("conversation_id")
extra.get("chat_model_config")
extra.get("use_mcp")
```

读取项目字段。

### 6.3 将字符串工具转换为 OpenAI 工具结构

如果调用方只传工具名称：

```json
{
  "tools": ["calculator"]
}
```

路由会通过 `get_tool()` 找到工具，然后转换为：

```json
{
  "type": "function",
  "function": {
    "name": "calculator",
    "description": "...",
    "parameters": {}
  }
}
```

为什么要转换：模型不能执行 Python 对象，它只能看到工具名称、说明和参数 Schema。结构化工具描述使模型能够生成合法参数。

### 6.4 从工具 Schema 还原项目工具配置

```python
tool_names = [x["function"]["name"] for x in body.tools]
tool_config = {
    name: get_tool_config(name)
    for name in tool_names
}
```

这里的 `tool_config` 不是模型看到的工具 Schema，而是项目内部用于筛选可执行工具的配置映射。

### 6.5 调用内部 `chat()`

```python
result = await chat(
    query=body.messages[-1]["content"],
    metadata=extra.get("metadata", {}),
    conversation_id=extra.get("conversation_id", ""),
    history_len=-1,
    stream=body.stream,
    chat_model_config=extra.get("chat_model_config", chat_model_config),
    tool_config=tool_config,
    use_mcp=extra.get("use_mcp", False),
    max_tokens=body.max_tokens,
)
```

当前实现只把 `body.messages` 中最后一条消息的 `content` 作为 `query`。Agent 使用的历史消息并不是直接来自本次请求的完整 `messages`，而是后面通过 `conversation_id` 从数据库读取。

### 6.6 本阶段交接：从接口模型切换到内部业务模型

路由已经把外部请求压缩成 S2。这里尤其要记住：当前实现只把最后一条 `messages` 的内容作为 `query`，历史消息将在内部根据 `conversation_id` 从数据库读取。

```python
# S2：传给 chat() 的核心参数
{
    "query": "请使用工具处理这个问题",
    "conversation_id": "conv-001",
    "stream": True,
    "tool_config": {"example_tool": ...},
    "chat_model_config": {},
    "use_mcp": False,
}
```

下一阶段以 S2 为输入，创建异步生成器，并开始准备模型、工具和 Agent。

## 7. 阶段四：`chat()` 建立异步输出入口

源码位置：

```text
chatchat/server/chat/chat.py:134-319
```

`chat()` 内部定义了异步生成器：

```python
async def chat_iterator_event():
    ...
```

为什么使用异步生成器：

- Agent 执行过程中会产生多个事件。
- 不需要等待整个任务结束才返回第一段内容。
- 可以用 `async for` 边执行、边读取、边发送。

`chat()` 本身负责选择两种响应模式：

```text
stream=true  → EventSourceResponse(chat_iterator_event())
stream=false → 服务端遍历 chat_iterator_event()，聚合后一次返回
```

因此流式和非流式不是两套 Agent 实现，只是同一事件生成器的两种消费方式。

### 7.1 本阶段交接：生成器是后续执行的容器

`chat()` 此时还没有直接得到完整回答。它建立 `chat_iterator_event()`，让后续模型、工具和 Callback 事件都能从同一个异步生成器输出。下一步进入这个生成器内部，先创建模型对象。

## 8. 阶段五：创建模型对象

### 8.1 读取四类模型配置

源码位置：

```text
chatchat/server/chat/chat.py:43-73
```

如果请求没有传入 `chat_model_config`：

```python
configs = configs or Settings.model_settings.LLM_MODEL_CONFIG
```

当前配置中通常包括：

```text
preprocess_model
llm_model
action_model
postprocess_model
image_model
```

Agent 决策真正使用的是：

```python
models["action_model"]
```

对应 `chat.py:92`。

### 8.2 模型名为空时使用默认 LLM

```python
model_name = params.get("model", "").strip() or get_default_llm()
```

当前学习环境中：

```text
DEFAULT_LLM_MODEL = qwen2:7b
```

所以 `action_model.model` 为空时，最终选择 `qwen2:7b`。

### 8.3 为 Agent 决策模型创建 `ChatPlatformAI`

```python
llm_params = get_ChatPlatformAIParams(...)
model_instance = ChatPlatformAI(**llm_params)
```

`get_ChatPlatformAIParams()` 位于：

```text
chatchat/server/utils.py:270-307
```

它调用 `get_model_info(model_name)`，从 `MODEL_PLATFORMS` 中找到：

```text
platform_name = ollama
model_name = qwen2:7b
api_base_url = http://127.0.0.1:11434/v1
api_key = EMPTY
```

然后组成：

```python
{
    "model": "qwen2:7b",
    "api_base": "http://127.0.0.1:11434/v1",
    "api_key": "EMPTY",
    "temperature": ...,
    "max_tokens": ...,
    "streaming": True,
}
```

### 8.4 `ChatPlatformAI` 创建模型平台客户端

源码位置：

```text
langchain_chatchat/chat_models/base.py:394-440
```

```python
values["client"] = openai.OpenAI(
    **client_params
).chat.completions
```

`client` 最终是 OpenAI SDK 的 `chat.completions` 资源对象。

当代码调用：

```python
self.client.create(messages=message_dicts, **params)
```

当前实际模型请求为：

```text
POST http://127.0.0.1:11434/v1/chat/completions
```

Ollama 实现了 OpenAI 兼容接口，因此 Chatchat 不需要调用 Ollama 私有的 `/api/chat`。

### 8.5 消息怎样转换为模型请求

源码位置：

```text
langchain_chatchat/chat_models/base.py:645-713
```

`_create_message_dicts()` 将 LangChain 的：

```text
SystemMessage
HumanMessage
AIMessage
ToolMessage
```

转换为 OpenAI `messages` 字典，再交给模型平台。

流式模式下 `_stream()`：

```python
for chunk in self.client.create(
    messages=message_dicts,
    stream=True,
    ...,
):
    yield chunk
```

虽然项目上层使用异步 Agent，但 `ChatPlatformAI` 当前内部创建的是同步 `openai.OpenAI`。LangChain 的 `BaseChatModel._astream()` 会通过线程执行器包装同步 `_stream()`，避免同步网络迭代直接阻塞事件循环。

### 8.6 本阶段交接：只完成模型适配，还没有调用模型

本阶段将模型配置转换成了 `ChatPlatformAI`，并确定真实模型端点是 Ollama 的 `/v1/chat/completions`。此时模型客户端已经准备好，但 Prompt 和 Agent 尚未创建，更没有发起推理请求。

```text
S3（部分完成）
  action_model = ChatPlatformAI(qwen2:7b, Ollama 地址)
```

下一阶段继续补齐 S3 中的工具、历史、工具轨迹和 MCP 连接。

## 9. 阶段六：选择可执行工具、加载历史和 MCP

### 9.1 筛选本地工具

源码位置：

```text
chatchat/server/chat/chat.py:168-170
```

```python
all_tools = get_tool().values()
tools = [
    tool for tool in all_tools
    if tool.name in tool_config
]
```

即使项目注册了很多工具，本次 Agent 只能执行请求允许的工具。

这样做的作用：

- 缩小模型的工具选择空间。
- 避免把所有工具暴露给每次请求。
- 减少 Prompt 中的工具说明长度。
- 降低误调用不相关工具的概率。

### 9.2 从数据库加载历史消息

源码位置：

```text
chatchat/server/chat/chat.py:80-91
```

```python
messages = filter_message(
    conversation_id=conversation_id,
    limit=history_len,
)
messages = list(reversed(messages))
```

数据库默认按时间倒序返回，代码再反转为正常对话顺序，并转换成：

```python
{"role": "user", "content": ...}
{"role": "assistant", "content": ...}
```

### 9.3 恢复之前的工具调用轨迹

```python
intermediate_steps = loads(
    messages[-1]["metadata"]["intermediate_steps"],
    ...,
)
```

`intermediate_steps` 不只是当前请求的临时变量，也可以从上一条数据库消息的元数据中恢复。

它保存：

```text
AgentAction：调用了哪个工具、参数是什么
Observation：工具返回了什么
```

### 9.4 加载 MCP 连接

源码位置：

```text
chatchat/server/chat/chat.py:94-127
```

数据库中的 MCP 连接会被转换为：

```text
stdio 连接配置
或
SSE 连接配置
```

只有 `use_mcp=True` 时，连接配置才传给 Agent：

```python
mcp_connections=mcp_connections if use_mcp else {}
```

### 9.5 本阶段交接：Agent 所需依赖已经收集齐

现在已经得到：

```python
# S3：创建 Agent 前的运行时材料
{
    "llm": models["action_model"],
    "tools": [example_tool_object],
    "history": [...],
    "intermediate_steps": [...],
    "mcp_connections": {},
}
```

下一阶段把这些材料交给注册器，分别创建“做一次决策的 agent”和“驱动多轮循环的 agent_executor”。

## 10. 阶段七：创建具体 Agent

### 10.1 固定选择 `platform-knowledge-mode`

源码位置：

```text
chatchat/server/chat/chat.py:119-127
```

```python
agent_executor = PlatformToolsRunnable.create_agent_executor(
    agent_type="platform-knowledge-mode",
    agents_registry=agents_registry,
    llm=llm,
    tools=tools,
    history=history,
    intermediate_steps=intermediate_steps,
    mcp_connections=...,
)
```

当前调用链没有根据模型名动态选择 `qwen`、`glm3` 等分支，而是固定使用 `platform-knowledge-mode`。

### 10.2 Agent 注册器创建执行器

源码位置：

```text
chatchat/server/agents_registry/agents_registry.py:199-218
```

注册器完成两层创建：

```text
create_platform_knowledge_agent()
    → 创建“Prompt | LLM | OutputParser”决策链

PlatformToolsAgentExecutor(...)
    → 创建负责多轮循环和工具执行的控制器
```

两者不能混为一谈：

| 对象 | 作用 |
|---|---|
| `agent` | 根据当前信息做一次决策 |
| `agent_executor` | 反复调用 agent，并在中间执行工具 |

### 10.3 为什么存在两个工具表示

`PlatformToolsRunnable.create_agent_executor()` 会准备：

```text
模型可见的工具 Schema
可真正执行的 BaseTool 对象
MCP 工具对象
```

模型只能读取工具描述，真正执行必须依靠 Python 工具对象。因此“告诉模型有哪些工具”和“真正执行工具”是两件事。

### 10.4 本阶段交接：先有 Executor，再放大观察其中的 agent

注册器已经把 S3 组装成 `PlatformToolsAgentExecutor`。Executor 内部持有一个 `agent`；本阶段只说明了两者职责，下一阶段专门展开这个 `agent` 的单轮决策流水线。

## 11. 阶段八：构建 Prompt、LLM 和输出解析器流水线

源码位置：

```text
langchain_chatchat/agents/structured_chat/platform_knowledge_bind.py:91-134
```

核心代码：

```python
agent = (
    RunnablePassthrough.assign(
        agent_scratchpad=lambda x:
            format_to_platform_tool_messages(
                x["intermediate_steps"]
            )
    )
    | prompt
    | llm
    | PlatformToolsAgentOutputParser(
        instance_type="platform-knowledge-mode"
    )
)
```

这是一条 LangChain Runnable 管道：

```text
输入字典
  │
  ├── 把 intermediate_steps 格式化成 agent_scratchpad
  ▼
ChatPromptTemplate
  │
  ▼
ChatPlatformAI
  │
  ▼
PlatformToolsAgentOutputParser
  │
  ├── AgentAction：需要执行工具
  └── AgentFinish：已经得到最终答案
```

### 11.1 Prompt 包含什么

Prompt 创建位置：

```text
langchain_chatchat/agents/react/create_prompt_template.py:162-197
```

消息顺序为：

```text
SystemMessage：角色、工具规则、本地工具、MCP 工具、工作目录
ChatHistory：历史对话
HumanMessage：当前用户问题和时间
AgentScratchpad：之前的工具调用和 Observation
```

为什么工具结果必须放在 Prompt 中：模型本身无法直接读取 Python 变量。只有把 Observation 转换为模型消息，下一轮模型才能知道工具返回了什么。

### 11.2 本阶段交接：对象全部创建完成，下一步才真正执行

现在 S3 已经完整变成以下对象层级：

```text
PlatformToolsRunnable
  └── PlatformToolsAgentExecutor       负责多轮循环
        └── agent Runnable             负责单轮决策
              agent_scratchpad
                → Prompt
                → ChatPlatformAI
                → OutputParser
```

到目前为止仍是“组装对象”。下一阶段调用 `full_chain.invoke()`，主执行链与状态输出链才开始同时运行。

## 12. 阶段九：启动后台 Agent，同时读取事件

### 12.1 `full_chain.invoke()` 返回异步迭代器

源码位置：

```text
chatchat/server/chat/chat.py:181-190
langchain_chatchat/agents/platform_tools/base.py:259-378
```

```python
chat_iterator = full_chain.invoke({"input": query})

async for item in chat_iterator:
    ...
```

`PlatformToolsRunnable.invoke()` 虽然是普通函数，但返回内部的异步生成器 `chat_iterator()`。

### 12.2 创建后台执行任务

```python
task = asyncio.create_task(
    wrap_done(
        self.agent_executor.ainvoke(...),
        self.callback.done,
    )
)
```

这里形成生产者和消费者：

```text
生产者：agent_executor.ainvoke()
    运行模型和工具，并触发回调事件

消费者：callback.aiter()
    从异步队列读取事件并 yield 给 chat.py
```

为什么使用 `asyncio.create_task()`：

如果直接：

```python
await self.agent_executor.ainvoke(...)
```

那么必须等整个 Agent 结束后才能开始读取事件，无法实时显示模型和工具状态。

`create_task()` 让 Agent 执行和事件消费在同一个事件循环中并发推进。

### 12.3 `wrap_done()` 的作用

源码位置：

```text
langchain_chatchat/agents/platform_tools/base.py:93-102
```

无论 Agent 正常结束还是发生异常，都会：

```python
event.set()
```

回调迭代器以此判断以后不会再产生新事件，从而退出等待。

### 12.4 本阶段交接：从这里开始分成主链与旁路

`create_task()` 启动 `agent_executor.ainvoke()`，这是主执行链；`callback.aiter()` 同时读取 Queue，这是状态输出链。为了先理解业务决策，下一阶段沿主执行链进入 `_acall()`；第 17 节再回来讲状态旁路。

## 13. 阶段十：真正的 Agent 多轮循环

源码位置：

```text
langchain_chatchat/agents/all_tools_agent.py:124-230
```

核心代码：

```python
while self._should_continue(iterations, time_elapsed):
    next_step_output = await self._atake_next_step(
        name_to_tool_map,
        color_mapping,
        inputs,
        intermediate_steps,
        run_manager=run_manager,
    )

    if isinstance(next_step_output, AgentFinish):
        return await self._areturn(...)

    intermediate_steps.extend(next_step_output)
    iterations += 1
```

### 13.1 `_should_continue()` 控制什么

该方法继承自 LangChain `AgentExecutor`，主要根据：

```text
最大迭代次数
最大执行时间
```

决定是否继续，防止模型无限调用工具。

项目外层还使用：

```python
async with asyncio_timeout(self.max_execution_time):
```

提供整体超时保护。

### 13.2 一轮 `_atake_next_step()` 做什么

该方法继承自当前 LangChain：

```text
/home/lab239/anaconda3/envs/Langchain-Chatchat/
lib/python3.10/site-packages/langchain/agents/agent.py
```

核心过程：

```python
output = await self.agent.aplan(
    intermediate_steps,
    callbacks=...,
    **inputs,
)
```

`aplan()` 会运行前面构造的：

```text
agent_scratchpad → prompt → llm → output parser
```

然后有两种结果：

```text
AgentAction：模型决定调用工具
AgentFinish：模型决定结束并给出最终答案
```

### 13.3 模型一次可以选择多个工具

LangChain 会把输出统一转换为 `actions` 列表，并通过：

```python
await asyncio.gather(...)
```

并发执行同一轮中的多个工具。

因此项目支持两种组合：

```text
串行多轮：模型 → 工具 A → 模型 → 工具 B → 模型

单轮并发：模型 → [工具 A、工具 B] → 收集结果 → 模型
```

### 13.4 本阶段交接：`aplan()` 还不会直接执行工具

`agent.aplan()` 运行完 Prompt、LLM 和 OutputParser 后，先产出结构化决策。只有决策是 `AgentAction` 时，Executor 才进入工具执行；如果是 `AgentFinish`，主循环直接结束。因此必须先理解解析器输出，再看工具执行。

## 14. 阶段十一：模型输出怎样变成 Action 或 Finish

源码位置：

```text
langchain_chatchat/agents/output_parsers/platform_tools.py:60-104
```

当前使用：

```python
PlatformToolsAgentOutputParser(
    instance_type="platform-knowledge-mode"
)
```

所以解析进入：

```python
self.knowledge_parser.parse_result(...)
```

输出解析器承担模型输出与程序控制之间的协议边界：

```text
模型输出
    │
    ├── 识别出工具名和参数 → AgentAction
    └── 已经能够回答问题   → AgentFinish
```

`AgentAction` 主要携带：

```text
tool        工具名
tool_input  工具参数
log         产生该动作时的文本
```

模型不会直接执行 Python/MCP 工具，只生成调用意图。OutputParser 把意图变成 `AgentAction`，下一阶段才由 Executor 执行。

### 14.1 本阶段交接：得到 S4 的前半部分

```python
# S4（尚未包含 Observation）
AgentAction(
    tool="example_tool",
    tool_input={"input": "..."},
    log="...",
)
```

如果这里得到 `AgentFinish`，就不进入工具执行；如果得到 `AgentAction`，交给 `_aperform_agent_action()`。

## 15. 阶段十二：工具真正执行并产生 Observation

源码位置：

```text
langchain_chatchat/agents/all_tools_agent.py:315-388
```

### 15.1 执行普通本地工具

```python
observation = await tool.arun(
    agent_action.tool_input,
    ...,
)
```

输入：

```text
agent_action.tool_input
```

输出：

```text
observation
```

### 15.2 执行 MCP 工具

```python
observation = await mcp_tool.arun(
    agent_action.tool_input,
    ...,
)
```

MCP 工具还会根据：

```text
tool name
server name
```

定位具体 MCP Server 中的工具。

### 15.3 工具不存在时

如果模型生成的工具名不在 `name_to_tool_map` 中，则执行 `InvalidTool`，把以下信息作为 Observation：

```text
模型请求的工具名
当前允许的工具名列表
```

这使模型有机会在下一轮修正工具选择，而不是让程序直接因 KeyError 崩溃。

### 15.4 统一返回 `AgentStep`

```python
return AgentStep(
    action=agent_action,
    observation=observation,
)
```

`AgentStep` 把“模型做出的动作”和“工具执行结果”绑定在一起。

### 15.5 本阶段交接：S4 已经完整

```python
S4 = (
    AgentAction(tool="example_tool", tool_input={"input": "..."}),
    "工具返回的 Observation",
)
```

工具执行到这里已经结束，但 Agent 尚未结束。下一阶段把 S4 写入 `intermediate_steps`，重新送回同一个单轮决策流水线。

## 16. 阶段十三：工具结果怎样重新喂给模型

### 16.1 保存到 `intermediate_steps`

源码位置：

```text
langchain_chatchat/agents/all_tools_agent.py:163
```

```python
intermediate_steps.extend(next_step_output)
```

逻辑结构可以理解为：

```python
intermediate_steps = [
    (
        AgentAction(
            tool="calculator",
            tool_input={"expression": "1+1"},
            log="...",
        ),
        "2",
    )
]
```

### 16.2 转换成模型消息

源码位置：

```text
langchain_chatchat/agents/format_scratchpad/all_tools.py:56-136
```

对标准工具调用，会生成：

```text
AIMessage：记录模型上一次发出的工具调用
ToolMessage：记录工具返回的 Observation
```

对通用 `AgentAction`，会生成：

```text
AIMessage(content=agent_action.log)
HumanMessage(content=str(observation))
```

### 16.3 下一轮再次进入模型

下一次执行 `self.agent.aplan()` 时：

```python
agent_scratchpad=lambda x:
    format_to_platform_tool_messages(
        x["intermediate_steps"]
    )
```

会重新计算 `agent_scratchpad`。

这就是“工具输出喂给模型”的完整代码实现：

```text
tool.arun()
  → observation
  → AgentStep
  → intermediate_steps
  → format_to_platform_tool_messages()
  → agent_scratchpad
  → Prompt
  → LLM
```

### 16.4 本阶段交接：闭环在这里形成

新的 `intermediate_steps` 再次进入 `agent.aplan()`：

```text
S4 → intermediate_steps → agent_scratchpad → Prompt → LLM → OutputParser
```

如果解析成新 `AgentAction`，流程回到第 15 节执行下一个工具；如果解析成 `AgentFinish`，主执行链结束。与此同时，每一轮模型和工具事件都已经写入 Callback Queue。下一阶段切换到并行的状态输出链。

## 17. 阶段十四：状态回调怎样实时反映执行过程

源码位置：

```text
langchain_chatchat/callbacks/agent_callback_handler.py:32-328
```

### 17.1 状态编号

| 状态 | 数值 | 含义 |
|---|---:|---|
| `chain_start` | 0 | 整条 Agent Chain 开始 |
| `llm_start` | 1 | 一次模型调用开始 |
| `llm_new_token` | 2 | 模型产生一个新 Token/片段 |
| `llm_end` | 3 | 一次模型调用结束 |
| `agent_action` | 4 | 模型输出被解析为工具动作 |
| `agent_finish` | 5 | Agent 得到最终结果 |
| `tool_require_approval` | 6 | 工具需要审批 |
| `tool_start` | 7 | 工具开始执行 |
| `tool_end` | 8 | 工具执行完成 |
| `error` | -1 | 发生错误 |
| `chain_end` | -999 | 整条 Chain 结束 |

### 17.2 常见事件顺序

一个调用一次工具的请求，通常可以观察为：

```text
chain_start
llm_start
llm_new_token ...
llm_end
agent_action
tool_start
tool_end
llm_start
llm_new_token ...
llm_end
agent_finish
chain_end
```

具体事件次序还会受到模型流式输出、工具类型和 LangChain 回调顺序影响，但语义关系不变。

### 17.3 四个最重要的业务状态

#### `PlatformToolsAction`

表示模型已经决定调用工具，包含：

```text
tool
tool_input
log
```

这时工具不一定已经开始执行。

#### `PlatformToolsActionToolStart`

表示具体工具的 `run/arun` 已开始。

#### `PlatformToolsActionToolEnd`

表示工具执行结束，包含：

```text
tool
tool_output
```

这只是一次工具结束，不代表整个 Agent 结束。

#### `PlatformToolsFinish`

表示整个 Agent 已结束，包含最终：

```text
return_values
log
```

### 17.4 回调队列为什么存在

回调处理器内部维护：

```python
self.queue = asyncio.Queue()
self.done = asyncio.Event()
```

模型和工具回调把事件写入 `queue`，`PlatformToolsRunnable` 从 `queue` 读取。

这样 Agent 控制逻辑不需要直接依赖 WebUI 或 SSE；同一个 Agent 执行过程可以被不同输出层消费。

### 17.5 本阶段交接：Queue 中是原始事件，还不是 HTTP JSON

Callback 只负责将主执行链事件写入 `asyncio.Queue`。`PlatformToolsRunnable.invoke()` 消费 Queue，并把状态码转换成 `PlatformToolsAction`、`PlatformToolsActionToolEnd` 等项目对象；这些对象随后 `yield` 回 `chat.py`。下一阶段从这个汇合点继续。

## 18. 阶段十五：内部状态转换成 API 响应

源码位置：

```text
chatchat/server/chat/chat.py:190-275
```

`chat.py` 根据对象类型转换数据。

### 18.1 Agent 决定调用工具

```python
if isinstance(item, PlatformToolsAction):
```

生成 OpenAI 风格：

```json
{
  "type": "function",
  "function": {
    "name": "工具名",
    "arguments": {}
  }
}
```

### 18.2 工具开始

```python
elif isinstance(item, PlatformToolsActionToolStart):
```

创建 `last_tool`，记录工具名、参数和运行 ID。

### 18.3 工具结束

```python
elif isinstance(item, PlatformToolsActionToolEnd):
```

把：

```python
tool_output=item.tool_output
```

补充到 `last_tool`，然后发送给客户端。

### 18.4 模型 Token

```python
elif isinstance(item, PlatformToolsLLMStatus):
    data["text"] = item.text
```

模型输出文本作为 `content` 返回。

### 18.5 Agent 最终结束

```python
elif isinstance(item, PlatformToolsFinish):
    data["text"] = item.log
```

然后统一构造：

```python
ret = OpenAIChatOutput(
    object="chat.completion.chunk",
    content=data.get("text", ""),
    tool_calls=data["tool_calls"],
    status=data["status"],
    ...,
)
```

### 18.6 本阶段交接：内部对象已经变成统一输出模型

无论上游是模型 Token、工具开始、工具结果还是 AgentFinish，`chat.py` 都把它整理为一个 `OpenAIChatOutput`。下一阶段只负责将这个 Pydantic 对象序列化成 OpenAI 风格字典。

## 19. 阶段十六：OpenAIChatOutput 怎样序列化

源码位置：

```text
chatchat/server/api_server/api_schemas.py:115-176
```

### 19.1 流式块

当：

```python
object == "chat.completion.chunk"
```

输出结构为：

```json
{
  "object": "chat.completion.chunk",
  "status": 2,
  "choices": [
    {
      "delta": {
        "content": "一个文本片段",
        "tool_calls": []
      },
      "role": "assistant"
    }
  ]
}
```

### 19.2 非流式响应

当：

```python
object == "chat.completion"
```

输出结构为：

```json
{
  "object": "chat.completion",
  "choices": [
    {
      "message": {
        "role": "assistant",
        "content": "完整回答",
        "tool_calls": []
      }
    }
  ]
}
```

### 19.3 本阶段交接：S5 已经形成

```text
S5：OpenAI 风格响应块
  content      模型文本
  tool_calls   工具名、参数和结果
  status       当前 Agent/LLM/Tool 状态
  message_id   数据库消息 ID
```

下一阶段只决定 S5 是逐块发送，还是在服务端先聚合。

## 20. 阶段十七：流式和非流式返回

### 20.1 流式模式

源码位置：

```text
chatchat/server/chat/chat.py:295-296
```

```python
return EventSourceResponse(
    chat_iterator_event()
)
```

`EventSourceResponse` 会持续消费异步生成器，每次 `yield` 就向客户端发送一条 SSE 数据。

好处：

- 用户可以立即看到生成内容。
- WebUI 可以实时显示工具开始和结束。
- 长任务不必等完整结果生成后才返回。

### 20.2 非流式模式

源码位置：

```text
chatchat/server/chat/chat.py:297-319
```

非流式模式仍然遍历同一个 `chat_iterator_event()`：

```python
async for chunk in chat_iterator_event():
    ret.content += text
```

区别只是服务端先聚合所有文本，最后一次性返回。

这样可以避免维护两套 Agent 调用逻辑。

### 20.3 本阶段交接：后端执行逻辑相同，消费位置不同

流式模式由浏览器端 OpenAI SDK 逐块消费 S5；非流式模式由后端先消费并拼接，再返回完整 JSON。接下来回到最初的 Streamlit 调用点，看 S5 如何改变页面。

## 21. 阶段十八：WebUI 根据状态更新页面

源码位置：

```text
chatchat/webui_pages/dialogue/dialogue.py:435-524
```

WebUI 的处理规则包括：

| 状态 | 页面行为 |
|---|---|
| `llm_start` | 显示“正在解读工具输出结果...” |
| `llm_new_token` | 追加文本并以 streaming 状态刷新 |
| `llm_end` | 将本轮模型文本标记为完成 |
| `tool_start` | 展示工具名和输入参数 |
| `tool_end` | 展示 Observation；图片结果按图片处理 |
| `agent_finish` | 使用最终内容更新回答 |
| `error` | 使用 Streamlit 错误组件展示异常 |

所以用户在页面上看到的“正在调用工具”“Observation”“最终回答”，对应的是后端真实状态，不是 WebUI 自己推测的阶段。

### 21.1 本阶段交接：用户已看到回答，后端还要持久化

页面显示不是链路的最后一步。异步生成器结束前，`chat.py` 还需要把最终回答和 `intermediate_steps` 写回数据库，供同一会话的下一次请求恢复。

## 22. 阶段十九：保存消息和工具轨迹

### 22.1 创建消息记录

源码位置：

```text
chatchat/server/chat/chat.py:181-185
chatchat/server/db/repository/message_repository.py:8-33
```

Agent 开始执行前会新增消息：

```python
message_id = add_message_to_db(
    chat_type="llm_chat",
    query=query,
    conversation_id=conversation_id,
)
```

此时 `response` 默认为空字符串。

### 22.2 Agent 结束后更新消息

源码位置：

```text
chatchat/server/chat/chat.py:277-284
```

```python
update_message(
    message_id,
    agent_executor.history[-1]["content"],
    metadata={
        "intermediate_steps": string_intermediate_steps
    },
)
```

最终保存：

```text
query：用户问题
response：Agent 最终回答
metadata.intermediate_steps：工具调用和 Observation
```

### 22.3 为什么历史查询忽略空回答

源码位置：

```text
chatchat/server/db/repository/message_repository.py:74-92
```

```python
filter(MessageModel.response != "")
```

Agent 运行期间刚插入的消息还没有回答，不能作为历史再次传给当前模型，因此查询历史时过滤空回答。

### 22.4 本阶段交接：本次结果会成为下一次请求的输入

```text
本次 update_message()
  → 保存 history 与 intermediate_steps
  → 下一次相同 conversation_id 请求
  → 第 9 节重新加载这些数据
```

至此端到端链路闭合。下一节不再引入新模块，只用一个两轮工具示例把 S0～S5 连续复盘一遍。

## 23. 用一次两轮工具调用串起全部过程

下面的 `weather` 和 `clothing_advice` 是用于理解流程的假设工具，不表示当前项目已经注册这两个工具。

假设用户问：

```text
先查询北京天气，再根据温度建议穿什么衣服。
```

### 第一轮模型调用

模型收到：

```text
System Prompt
历史对话
用户问题
空的 agent_scratchpad
```

模型输出：

```text
AgentAction(
    tool="weather",
    tool_input={"city": "北京"}
)
```

### 第一次工具执行

Executor 调用：

```python
await weather.arun({"city": "北京"})
```

得到：

```text
Observation：北京当前 8℃，有风。
```

保存：

```python
intermediate_steps = [
    (weather_action, "北京当前 8℃，有风。")
]
```

### 第二轮模型调用

`intermediate_steps` 被转换为：

```text
AIMessage：调用 weather(city=北京)
ToolMessage：北京当前 8℃，有风。
```

模型可能认为信息仍不足，再输出：

```text
AgentAction(
    tool="clothing_advice",
    tool_input={"temperature": 8, "windy": true}
)
```

### 第二次工具执行

得到：

```text
Observation：建议穿外套并注意防风。
```

`intermediate_steps` 现在包含两次调用。

### 第三轮模型调用

模型获得两个工具的结果，输出：

```text
AgentFinish(
    output="北京当前约 8℃且有风，建议穿外套并注意防风。"
)
```

Executor 检测到 `AgentFinish` 后退出 `while`，回调发出 `agent_finish`，API 将最终答案返回 WebUI。

### 23.1 用数据快照复盘这次请求

| 快照 | 此时的数据 | 如何交给下一步 |
|---|---|---|
| S0 | 问题、模型名、工具名、会话 ID | OpenAI SDK 发送 HTTP JSON |
| S1 | `OpenAIChatInput` 和 `model_extra` | 路由提取内部参数 |
| S2 | `query/tool_config/conversation_id` | `chat()` 创建运行时对象 |
| S3 | 模型、工具、历史、Executor、Callback | `ainvoke()` 启动主循环 |
| S4-1 | `weather Action + 天气 Observation` | 写入 `intermediate_steps` 后再次调用模型 |
| S4-2 | `clothing Action + 穿衣 Observation` | 再次写入 `intermediate_steps` |
| S5 | `AgentFinish`、状态块和最终答案 | SSE 返回页面并写入数据库 |

现在可以看出，章节之间真正传递的不是类名，而是逐步变化的数据。类只是处理这些数据的执行者。

## 24. “模型思考”在代码中究竟指什么

源码中没有单独的：

```python
model.think()
```

所谓“模型思考并决定下一步”，在程序结构上对应：

```text
构造 Prompt
  → 调用 LLM
  → 解析模型输出
  → 得到 AgentAction 或 AgentFinish
```

因此可以使用下面的面试表达：

> Agent 的决策并不是独立于模型的一个判断函数，而是由 Prompt 约束模型输出格式，再由 OutputParser 将模型输出解析成 AgentAction 或 AgentFinish。AgentExecutor 根据解析结果决定执行工具还是结束；工具 Observation 被写入 intermediate_steps，并在下一轮格式化为 agent_scratchpad 重新输入模型。

不要把模型内部不可见的推理过程与项目中可观察的 `AgentAction.log`、Token 回调或 `intermediate_steps` 混为一谈。

## 25. 为什么项目采用这种分层

### 25.1 API 路由与 Agent 实现分离

路由只处理 HTTP 和参数，Agent 层只处理决策与工具循环。这样 Agent 可以被 WebUI、脚本或其他接口复用。

### 25.2 模型决策与工具执行分离

模型只能输出工具意图，不能直接运行 Python 函数。这使工具可以做参数校验、权限控制、日志记录和异常处理。

### 25.3 `intermediate_steps` 作为统一状态

它同时支持：

- 下一轮模型获取 Observation；
- 调试 Agent 为什么做出某个决定；
- 保存到数据库后恢复工具轨迹；
- 最终返回中间步骤。

### 25.4 回调事件与主循环分离

Agent 主循环不需要了解 Streamlit 和 SSE，只负责触发标准回调。输出层可以独立决定怎样展示状态。

### 25.5 同一异步生成器支持两种 HTTP 模式

流式直接向外发送，非流式在服务端聚合，减少重复业务代码。

### 25.6 OpenAI 兼容模型层

只要模型平台提供 OpenAI 兼容接口，应用层就可以用大致相同的方式访问 Ollama、Xinference、OneAPI 或云端模型。

## 26. 当前源码中的重要实现现状

以下内容是对当前提交的源码描述，不代表理想设计。

### 26.1 请求中的 `model` 没有直接决定 Agent 模型

路由读取 `body.model` 创建了：

```python
client = get_OpenAIClient(...)
```

但该局部变量后面没有被使用。内部 `chat()` 创建模型时，主要读取：

```text
extra_body.chat_model_config
或
Settings.model_settings.LLM_MODEL_CONFIG
```

因此，只修改请求顶层 `model`，不一定能改变 Agent 实际使用的 `action_model`。

### 26.2 请求的完整 `messages` 没有进入 Agent

路由只传递：

```python
body.messages[-1]["content"]
```

内部历史来自数据库 `conversation_id`。这与标准 OpenAI 接口通常由调用方直接提供完整 messages 的语义不同。

### 26.3 `tool_choice` 转换后没有继续传给 `chat()`

路由会把字符串 `tool_choice` 转成 OpenAI 工具选择结构，但调用内部 `chat()` 时没有传递 `body.tool_choice`。当前主链路主要使用 `body.tools` 生成 `tool_config`。

### 26.4 路由和 `chat()` 都可能插入消息

路由在存在 `conversation_id` 时调用一次 `add_message_to_db()`；`chat_iterator_event()` 中又无条件调用一次，并覆盖局部 `message_id`。

这解释了为什么数据库历史查询专门过滤 `response == ""` 的记录，也提示这里存在重复空消息记录的可能。

### 26.5 `full_chain` 的类型标注与实际数据形状不一致

当前代码：

```python
full_chain = {"chat_input": lambda x: x["input"]} | agent_executor
```

LangChain Runnable 前一段实际输出：

```python
{"chat_input": query}
```

下一段 `PlatformToolsRunnable.invoke()` 接收到的是整个字典，而它的形参标注为 `chat_input: str`。阅读时不能假设 LCEL 会根据形参名自动把字典拆成字符串。

### 26.6 `agent_finish` 存在重复条件分支

`platform_tools/base.py:334` 和 `341` 连续判断：

```python
elif data["status"] == AgentStatus.agent_finish:
```

第二个分支永远不可达，属于死代码。当前第一个分支已经生成 `PlatformToolsFinish`，因此通常不阻塞 Agent 完成，但结束事件处理逻辑需要后续整理。

这些现状应在未来优化时分别设计复现用例，再决定修复方式。本文只记录调用链，没有修改相关源码，也没有将它们自动写入项目缺陷清单。

## 27. 阅读源码时最容易混淆的地方

### 27.1 `chat.py` 的 `async for` 不是 Agent 循环

它只消费状态。Agent 循环是 `PlatformToolsAgentExecutor._acall()` 中的 `while`。

### 27.2 `AgentAction` 不等于工具已经执行

它只代表模型做出工具调用决策。真正开始执行对应 `tool_start`。

### 27.3 `tool_end` 不等于 Agent 结束

工具结果还需要回灌给模型。只有 `AgentFinish/agent_finish` 才表示整个任务结束。

### 27.4 `llm_end` 不等于最终回答

一次 Agent 任务可能调用模型多次。每次模型调用都会产生一次 `llm_start/llm_end`。

### 27.5 工具 Schema 不等于可执行工具对象

Schema 供模型理解；`BaseTool/MCPStructuredTool` 才负责真实执行。

### 27.6 SSE 与异步不是同一概念

- `asyncio` 负责服务端任务并发和非阻塞等待。
- SSE 是服务端向客户端持续发送事件的 HTTP 协议形式。

## 28. 面试复述版本

### 28.1 一分钟版本

> Langchain-Chatchat 的 Agent 接口由 FastAPI 提供 OpenAI 兼容请求。路由把用户最后一条消息、工具配置、会话 ID 和 MCP 开关传入内部 chat 函数。chat 根据配置创建 action_model，并从数据库恢复历史和 intermediate_steps，然后通过 PlatformToolsRunnable 创建 PlatformToolsAgentExecutor。Executor 在异步 while 循环中调用 agent.aplan，agent 由 agent_scratchpad、Prompt、LLM 和 OutputParser 组成。模型输出 AgentAction 时，Executor 执行本地或 MCP 工具，把 Observation 加入 intermediate_steps，下一轮再格式化成 agent_scratchpad 喂给模型；输出 AgentFinish 时结束。模型和工具的过程事件通过 Callback 写入异步队列，chat.py 转换成 OpenAIChatOutput，流式模式由 SSE 实时返回，非流式模式则在服务端聚合后返回。最终回答和 intermediate_steps 会写回消息数据库。

### 28.2 关键术语

```text
AgentAction       模型产生的工具调用意图
Observation       工具返回结果
intermediate_steps 历史 Action 与 Observation
agent_scratchpad  将 intermediate_steps 转成模型可读消息
AgentFinish       Agent 最终回答和终止信号
Callback          执行状态的旁路通知机制
SSE               向浏览器持续推送状态和 Token
```

## 29. 源码导航

| 阅读顺序 | 文件 | 重点 |
|---:|---|---|
| 1 | `chatchat/webui_pages/dialogue/dialogue.py` | WebUI 请求参数和页面状态处理 |
| 2 | `chatchat/server/api_server/server_app.py` | FastAPI 和路由注册 |
| 3 | `chatchat/server/api_server/api_schemas.py` | OpenAI 输入输出结构 |
| 4 | `chatchat/server/api_server/chat_routes.py` | Agent 统一接口和参数转换 |
| 5 | `chatchat/server/chat/chat.py` | 模型、工具、历史、Agent 和响应主编排 |
| 6 | `chatchat/server/utils.py` | 模型平台解析和客户端参数 |
| 7 | `langchain_chatchat/chat_models/base.py` | OpenAI 兼容模型请求与流式输出 |
| 8 | `chatchat/server/agents_registry/agents_registry.py` | Agent 类型注册和 Executor 创建 |
| 9 | `langchain_chatchat/agents/platform_tools/base.py` | Agent 包装、后台任务和事件转换 |
| 10 | `langchain_chatchat/agents/all_tools_agent.py` | Agent 多轮循环和工具执行 |
| 11 | `langchain_chatchat/agents/structured_chat/platform_knowledge_bind.py` | Prompt、LLM、Parser 管道 |
| 12 | `langchain_chatchat/agents/format_scratchpad/all_tools.py` | Observation 回灌模型 |
| 13 | `langchain_chatchat/agents/output_parsers/platform_tools.py` | Action/Finish 解析 |
| 14 | `langchain_chatchat/callbacks/agent_callback_handler.py` | 状态队列和回调事件 |
| 15 | `chatchat/server/db/repository/message_repository.py` | 消息新增、更新和历史加载 |

## 30. 本文验收问题

完成本文学习后，应能够不看文档回答：

1. `/chat/chat/completions` 为什么包含两个 `chat`？
2. `OpenAIChatInput.Config.extra = "allow"` 有什么作用？
3. 当前 `action_model` 为什么最终使用 `qwen2:7b`？
4. Chatchat 请求 Ollama 的实际 URL 是什么？
5. `agent` 和 `agent_executor` 的职责有什么区别？
6. 真正的 Agent `while` 循环在哪个函数？
7. 模型输出怎样变成 `AgentAction`？
8. 工具在哪里执行，返回值保存在哪里？
9. `intermediate_steps` 怎样变成下一轮 Prompt？
10. `tool_end` 为什么不是整个 Agent 的结束？
11. `create_task()` 和回调队列为什么缺一不可？
12. 流式和非流式为什么能够复用同一个异步生成器？
13. 最终回答和工具轨迹保存在哪张表对应的数据中？
14. 当前请求顶层 `model` 是否一定决定 Agent 实际模型？

当这些问题都能结合文件、函数和数据结构回答时，才算真正理解了本项目 Agent 对话的主调用链。
