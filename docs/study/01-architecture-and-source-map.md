# 架构与源码地图

## 1. 先建立正确的边界

Langchain-Chatchat 不是大模型训练框架，也不应该把所有模型权重直接加载到应用进程中。它主要负责：

- 接收聊天、知识库和 Agent 请求。
- 管理文档、知识库、会话和消息。
- 调用 Embedding、LLM、Reranker 等模型 API。
- 编排检索、Prompt、工具和 Agent 循环。
- 通过 FastAPI 暴露接口，通过 Streamlit 提供 WebUI。

系统可以分为三个独立边界：

```text
交互层：Streamlit / API / SDK
应用层：Chat / RAG / Agent / Knowledge Base
模型层：Xinference / Ollama / OpenAI-compatible provider
```

学习时每遇到一个函数，先判断它属于哪一层。

## 2. 仓库结构

```text
Langchain-Chatchat/
├── libs/
│   ├── chatchat-server/                 # 学习主目录
│   │   ├── chatchat/                    # 完整应用
│   │   ├── langchain_chatchat/          # LangChain 扩展和 Agent 实现
│   │   ├── tests/                       # API、RAG、Agent、MCP 测试
│   │   └── pyproject.toml               # 服务包真实依赖
│   └── python-sdk/                      # Python 客户端 SDK
├── docker/                              # 镜像与 Compose
├── docs/                                # 用户和开发文档
├── markdown_docs/                       # 旧版/补充模块文档
├── tools/                               # 模型加载等辅助脚本
└── pyproject.toml                       # 根目录聚合配置，不是主服务依赖入口
```

主源码根目录是：

```text
libs/chatchat-server
```

IDE 中应将该目录标记为源码/项目根目录，避免 Python 导入跳转失败。

## 3. 两个 Python 包的职责

### 3.1 `chatchat`：应用层

[`../../libs/chatchat-server/chatchat`](../../libs/chatchat-server/chatchat) 包含：

- `cli.py`：`chatchat init/kb/start` 命令入口。
- `startup.py`：使用多进程启动 FastAPI 与 Streamlit。
- `settings.py`：YAML 配置模型和默认值。
- `server/api_server`：FastAPI 应用与路由。
- `server/chat`：普通对话、知识库问答、文件问答。
- `server/knowledge_base`：知识库服务和向量库适配器。
- `server/file_rag`：文档加载、分块和 Retriever。
- `server/db`：SQLAlchemy 模型、Session 和 Repository。
- `server/agent`：应用侧工具定义与注册。
- `server/agents_registry`：根据配置构造 AgentExecutor。
- `webui_pages`：Streamlit 页面。

### 3.2 `langchain_chatchat`：框架扩展层

[`../../libs/chatchat-server/langchain_chatchat`](../../libs/chatchat-server/langchain_chatchat) 包含：

- `agents`：Agent、输出解析器、自定义执行器。
- `agent_toolkits`：平台工具、内置工具和 MCP 工具包装。
- `chat_models`：模型消息和模型适配扩展。
- `embeddings`：Embedding 适配。
- `callbacks`：Agent/流式事件回调。

可以把关系理解为：

```text
chatchat
  = 产品和业务逻辑

langchain_chatchat
  = 为产品提供的 LangChain 扩展能力
```

## 4. 启动链路

入口在 [`cli.py`](../../libs/chatchat-server/chatchat/cli.py)：

```text
chatchat start -a
  ↓ Click 命令解析
chatchat.cli.main
  ↓
chatchat.startup.main
  ↓
start_main_server
  ├── Process(run_api_server)
  │     └── create_app → uvicorn.run
  └── Process(run_webui)
        └── streamlit.bootstrap.run
```

`-a` 等价于同时启用 API 和 WebUI。默认端口定义在 [`settings.py`](../../libs/chatchat-server/chatchat/settings.py)：

- FastAPI：`7861`
- Streamlit：`8501`

首次阅读任务：在 `start_main_server` 中找出以下状态：

1. `args.all` 如何展开为 `api` 和 `webui`。
2. 为什么要使用两个 `multiprocessing.Process`。
3. `Event` 如何保证 API 启动后再启动 WebUI。
4. Ctrl+C 后父进程如何清理子进程。

## 5. 配置与数据目录

`CHATCHAT_ROOT` 决定配置和数据放在哪里：

```python
CHATCHAT_ROOT = Path(os.environ.get("CHATCHAT_ROOT", ".")).resolve()
```

`chatchat init` 会在该目录生成：

```text
basic_settings.yaml
model_settings.yaml
kb_settings.yaml
prompt_settings.yaml
tool_settings.yaml
data/
├── knowledge_base/
├── logs/
├── media/
└── temp/
```

配置职责：

| 文件 | 关注点 |
|---|---|
| `basic_settings.yaml` | API/WebUI 地址、数据目录、SQLite URI、HTTP 超时 |
| `model_settings.yaml` | 默认 LLM、Embedding、模型平台、API 地址和密钥 |
| `kb_settings.yaml` | FAISS/其他向量库、分块、Top K、阈值、分词器 |
| `prompt_settings.yaml` | 对话、RAG、Agent Prompt |
| `tool_settings.yaml` | 工具启用状态、参数和密钥 |

开发学习时务必把 `CHATCHAT_ROOT` 指向独立目录。这样重新初始化不会污染仓库，也不会误删真实数据。

## 6. FastAPI 路由地图

应用创建入口是 [`server_app.py`](../../libs/chatchat-server/chatchat/server/api_server/server_app.py)。`create_app()` 注册六组路由：

| Router | 文件 | 作用 |
|---|---|---|
| `chat_router` | `chat_routes.py` | 对话、知识库对话、文件对话、统一 Chat Completions |
| `kb_router` | `kb_routes.py` | 知识库和文档管理 |
| `tool_router` | `tool_routes.py` | 工具列表和直接调用 |
| `openai_router` | `openai_routes.py` | OpenAI 兼容模型代理接口 |
| `server_router` | `server_routes.py` | 服务状态和配置相关接口 |
| `mcp_router` | `mcp_routes.py` | MCP 连接、工具和 Prompt |

学习 API 时先访问：

```text
http://127.0.0.1:7861/docs
```

再将 Swagger 中的接口映射到上述路由文件。

## 7. 普通模型调用链

统一入口是：

```text
POST /chat/chat/completions
```

核心链路：

```text
chat_routes.chat_completions
  ↓ 解析 OpenAIChatInput 和 extra_body
get_OpenAIClient
  ↓ 根据 model_settings 找到模型平台
OpenAI AsyncClient
  ↓ HTTP
外部 OpenAI 兼容模型服务
  ↓
openai_request
  ↓
EventSourceResponse / JSON
```

[`openai_routes.py`](../../libs/chatchat-server/chatchat/server/api_server/openai_routes.py) 还实现了一层统一模型代理：

- `/v1/models`
- `/v1/chat/completions`
- `/v1/embeddings`
- `/v1/images/*`
- `/v1/files/*`

其中 `get_model_client()` 使用 `asyncio.Semaphore` 控制同一模型平台的并发，是学习异步资源控制的好例子。

## 8. RAG 入库链路

RAG 入库和 RAG 查询是两条不同链路，必须分开理解。

入库的大致流程：

```text
上传/扫描知识库文件
  ↓ kb_routes / kb_doc_api
KnowledgeFile
  ↓
文档 Loader（PDF、Word、PPT、图片、CSV 等）
  ↓
TextSplitter
  ↓
List[Document]
  ↓
Embedding.embed_documents
  ↓
KBService.do_add_doc
  ├── 向量与文本写入 FAISS
  └── 文件/文档元数据写入 SQLAlchemy
```

重要目录：

```text
server/file_rag/document_loaders
server/file_rag/text_splitter
server/knowledge_base/kb_doc_api.py
server/knowledge_base/kb_service/base.py
server/knowledge_base/kb_service/faiss_kb_service.py
server/db/models
server/db/repository
```

默认参数在 `KBSettings`：

- `CHUNK_SIZE = 750`
- `OVERLAP_SIZE = 150`
- `VECTOR_SEARCH_TOP_K = 3`
- `SCORE_THRESHOLD = 2.0`
- `TEXT_SPLITTER_NAME = ChineseRecursiveTextSplitter`

不要死记默认值；要通过实验理解它们如何影响召回。

## 9. RAG 查询链路

入口之一是：

```text
POST /chat/kb_chat
```

核心链路：

```text
chat_routes
  ↓
chat/kb_chat.py::kb_chat
  ↓
KBServiceFactory.get_service_by_name
  ↓
KBService.search_docs
  ↓
FaissKBService.do_search
  ↓
EnsembleRetrieverService
  ├── FAISS 向量检索
  └── BM25 + jieba 关键词检索
  ↓ 0.5 / 0.5 合并
Top K Documents
  ↓
可选 Reranker
  ↓
PromptTemplate：context + question
  ↓
LLM 流式生成
  ↓
答案 + source_documents
```

关键源码：

- [`kb_chat.py`](../../libs/chatchat-server/chatchat/server/chat/kb_chat.py)
- [`faiss_kb_service.py`](../../libs/chatchat-server/chatchat/server/knowledge_base/kb_service/faiss_kb_service.py)
- [`ensemble.py`](../../libs/chatchat-server/chatchat/server/file_rag/retrievers/ensemble.py)
- [`reranker.py`](../../libs/chatchat-server/chatchat/server/reranker/reranker.py)

当前 `ensemble.py` 固定以 `0.5/0.5` 合并 BM25 和向量 Retriever。这是一个很适合做参数实验和小改造的位置。

## 10. Agent 主链路

当 `/chat/chat/completions` 收到 `tools` 或 `tool_choice` 时，会进入工具或 Agent 分支。

概念模型：

```text
用户消息
  ↓
Agent Prompt + 可用工具描述
  ↓
LLM
  ├── AgentFinish ───────────────→ 最终回答
  └── AgentAction(tool, input)
          ↓
       执行工具
          ↓
       Observation
          ↓
   intermediate_steps
          └──────────────→ 再次交给 LLM
```

关键模块：

| 模块 | 职责 |
|---|---|
| `agents_registry.py` | 按 Agent 类型、模型和工具构建 AgentExecutor |
| `tools_registry.py` | `@regist_tool` 装饰器和全局工具注册表 |
| `agents/*` | Prompt、Agent 实现和输出解析 |
| `all_tools_agent.py` | 自定义 AgentExecutor 循环和 MCP 工具执行 |
| `callbacks/*` | 将 Agent 事件转换为流式输出 |

重点阅读 [`all_tools_agent.py`](../../libs/chatchat-server/langchain_chatchat/agents/all_tools_agent.py) 中：

- `_call` / `_acall`
- `_perform_agent_action` / `_aperform_agent_action`
- `_consume_next_step`
- `intermediate_steps`
- `max_iterations` 与 `max_execution_time`

这是整个 Agent 学习阶段最重要的文件。

## 11. 工具注册与执行

应用侧工具位于：

```text
chatchat/server/agent/tools_factory
```

最简单的示例是 [`calculate.py`](../../libs/chatchat-server/chatchat/server/agent/tools_factory/calculate.py)：

```python
@regist_tool(title="数学计算器")
def calculate(text: str = Field(description="a math expression")) -> float:
    ...
```

`@regist_tool` 会：

1. 使用 LangChain 的 `tool` 装饰器创建 `BaseTool`。
2. 从类型和 Pydantic Field 推导参数 Schema。
3. 设置工具名称、标题和描述。
4. 放入 `_TOOLS_REGISTRY`。

工具描述和参数描述会直接影响 LLM 是否选对工具，不能只关注函数实现。

更复杂的 RAG 工具示例是 [`search_local_knowledgebase.py`](../../libs/chatchat-server/chatchat/server/agent/tools_factory/search_local_knowledgebase.py)。它把知识库搜索结果包装为 `BaseToolOutput`，再格式化成 LLM 可读的 Context。

## 12. MCP 链路

MCP 相关代码分布在：

```text
server/api_server/mcp_routes.py
server/db/models/mcp_connection_model.py
server/db/repository/mcp_connection_repository.py
langchain_chatchat/agent_toolkits/mcp_kit
tests/integration_tests/mcp_platform_tools
```

调用路径：

```text
MCP Server 配置
  ↓ 存入数据库
MCP Client 建立 stdio/SSE 连接
  ↓
获取 tools/prompts/resources
  ↓
包装为 MCPStructuredTool
  ↓
Agent 产生 MCPToolAction
  ↓
PlatformToolsAgentExecutor 匹配 server_name + tool name
  ↓
调用远端 MCP Tool
```

在没有吃透普通 `@regist_tool` 前，不要提前进入 MCP。

## 13. 数据持久化

默认情况下存在三种数据：

| 数据 | 默认存储 | 示例 |
|---|---|---|
| 原始内容 | 文件系统 | `data/knowledge_base/<kb>/content` |
| 向量索引 | FAISS 本地目录 | 每个知识库/Embedding 对应索引 |
| 结构化元数据 | SQLite + SQLAlchemy | `data/knowledge_base/info.db` |

SQLAlchemy 使用分层结构：

```text
db/models      定义表结构
db/repository  封装查询和写入
db/session.py  管理 Session
```

阅读时选择“知识库”这一组即可：

```text
knowledge_base_model.py
knowledge_file_model.py
knowledge_base_repository.py
knowledge_file_repository.py
```

其他 Conversation/Message 模型可以等 API 阶段再看。

## 14. WebUI 的位置

Streamlit 入口是 [`webui.py`](../../libs/chatchat-server/chatchat/webui.py)，页面位于：

```text
webui_pages/dialogue
webui_pages/knowledge_base
webui_pages/model_config
webui_pages/mcp
```

主线只需要回答：

1. 页面如何组装请求。
2. 页面调用了哪个 API。
3. SSE/流式数据如何显示。
4. Session State 保存了什么。

不需要花大量时间研究 Streamlit 样式。

## 15. 测试地图

[`../../libs/chatchat-server/tests`](../../libs/chatchat-server/tests) 提供了很好的行为入口：

| 测试 | 学习用途 |
|---|---|
| `api/test_openai_wrap.py` | OpenAI 兼容接口 |
| `api/test_stream_chat_api.py` | 普通、Agent、RAG 流式对话 |
| `api/test_kb_api_request.py` | 知识库完整 CRUD |
| `api/test_tools.py` | 工具列表与直接调用 |
| `kb_vector_db/test_faiss_kb.py` | FAISS 服务行为 |
| `custom_splitter/test_different_splitter.py` | 分块器比较 |
| `unit_tests/test_mcp_prompts.py` | MCP Prompt 转换 |
| `integration_tests/mcp_platform_tools` | MCP 集成 |

不要第一次就运行全部测试。很多集成测试依赖模型服务、数据库或网络。每一阶段只运行对应的最小测试集。

## 16. 阅读优先级

### 第一优先级

```text
chatchat/cli.py
chatchat/startup.py
chatchat/settings.py
server/api_server/server_app.py
server/api_server/chat_routes.py
server/chat/kb_chat.py
server/knowledge_base/kb_service/base.py
server/knowledge_base/kb_service/faiss_kb_service.py
server/file_rag/retrievers/ensemble.py
server/agents_registry/agents_registry.py
server/agent/tools_factory/tools_registry.py
langchain_chatchat/agents/all_tools_agent.py
```

### 第二优先级

```text
server/knowledge_base/kb_doc_api.py
server/file_rag/document_loaders
server/file_rag/text_splitter
server/db/models
server/db/repository
server/api_server/openai_routes.py
langchain_chatchat/agents/output_parsers
langchain_chatchat/callbacks
langchain_chatchat/agent_toolkits/mcp_kit
```

### 后期按需

```text
非 FAISS 向量库适配器
WebUI 样式细节
图片、语音、绘图平台工具
旧迁移逻辑
名称包含 stale 的文件
```

## 17. 必须掌握的术语

| 术语 | 在本项目中的含义 |
|---|---|
| Document | LangChain 文本文档对象，包含 `page_content` 和 `metadata` |
| Chunk | 原始文档切分后的最小检索单位 |
| Embedding | 将文本转换为向量的模型调用 |
| Vector Store | 保存向量并进行相似度搜索的系统，默认 FAISS |
| Retriever | 给定 Query 返回相关 Document 的统一接口 |
| BM25 | 基于关键词统计的稀疏检索算法 |
| Reranker | 对初步召回结果重新排序的模型 |
| AgentAction | LLM 决定调用某个工具及参数 |
| Observation | 工具执行后返回给 Agent 的结果 |
| Scratchpad | Agent 历史步骤形成的推理上下文 |
| AgentFinish | Agent 决定终止并返回答案 |
| Tool Schema | 告诉 LLM 工具名称、描述、参数和必填项 |
| SSE | 服务端逐步推送事件的流式协议 |
| MCP | 统一暴露工具、资源和 Prompt 的协议 |

接下来进入[10 周学习计划](./02-ten-week-plan.md)。
