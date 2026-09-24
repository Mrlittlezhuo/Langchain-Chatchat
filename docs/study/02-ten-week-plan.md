# 10 周源码学习计划

## 使用方式

每周都按照相同闭环执行：

```text
提出问题 → 找入口 → 跟调用链 → 运行验证 → 小修改 → 测试 → 复述总结
```

不要因为某一天没有完成就跳周。阶段验收没有通过时，优先补齐关键实验，而不是机械进入下一周。

## 第 0 周：环境基线与首次运行

**时间：6～8 小时**

### 目标

- 使用独立 Python 3.11 环境安装源码依赖。
- 将模型服务和 Chatchat 应用分离。
- 生成独立学习数据目录。
- 跑通普通对话、知识库问答和 API 文档。
- 保存一份可复现的环境基线。

### 0.1 创建独立环境

项目主服务声明 Python `>=3.10,<3.12`，建议使用 3.11：

```bash
cd /home/lab239/chenzhuo/Langchain-Chatchat

conda create -n chatchat-study python=3.11 -y
conda activate chatchat-study

python --version
which python
```

不要直接使用 `base` 环境。模型推理框架也不要与 Chatchat 安装进同一个 Python 环境。

### 0.2 安装 Poetry 和项目依赖

```bash
python -m pip install -U pip poetry

cd /home/lab239/chenzhuo/Langchain-Chatchat/libs/chatchat-server
poetry env use "$(which python)"
poetry install --with lint,test
```

如果确定使用 Xinference 客户端，再安装 extra：

```bash
poetry install --with lint,test -E xinference
```

验证：

```bash
poetry run python --version
poetry run python -c "import chatchat, langchain, fastapi, streamlit; print(chatchat.__version__)"
poetry run pytest --collect-only -q
```

### 0.3 选择一个模型服务

主线只选一个 OpenAI 兼容模型服务：

- 已有可用 OpenAI 兼容 API：最省时间，推荐用于源码学习。
- Ollama：适合单机轻量模型。
- Xinference：适合同时管理 LLM、Embedding 和 Reranker，但部署更重。

最低要求：

1. 一个 Chat LLM。
2. 一个 Embedding 模型。
3. Reranker 可在第 4 周后再添加。

先用模型服务自己的接口验证，不要直接把所有问题归因于 Chatchat：

```bash
curl http://127.0.0.1:<model-port>/v1/models
```

### 0.4 使用独立数据目录

```bash
export CHATCHAT_ROOT=/home/lab239/chenzhuo/chatchat-study-data
mkdir -p "$CHATCHAT_ROOT"

cd /home/lab239/chenzhuo/Langchain-Chatchat/libs/chatchat-server
poetry run python chatchat/cli.py init
```

把导出命令加入专用启动脚本或 Conda 激活脚本，但不要让不同项目共用同一 `CHATCHAT_ROOT`。

初始化后检查：

```bash
find "$CHATCHAT_ROOT" -maxdepth 2 -type f | sort
```

### 0.5 配置模型

编辑：

```text
$CHATCHAT_ROOT/model_settings.yaml
```

至少核对：

- `DEFAULT_LLM_MODEL`
- `DEFAULT_EMBEDDING_MODEL`
- `MODEL_PLATFORMS` 中的模型名称
- OpenAI 兼容 API 地址
- API Key（如果需要）

配置名必须与模型服务 `/v1/models` 返回的 ID 一致。

### 0.6 初始化知识库并启动

只有在 Embedding 模型已经可用时，才执行：

```bash
cd /home/lab239/chenzhuo/Langchain-Chatchat/libs/chatchat-server
poetry run python chatchat/cli.py kb -r
poetry run python chatchat/cli.py start -a
```

访问：

```text
API 文档：http://127.0.0.1:7861/docs
WebUI：http://127.0.0.1:8501
```

### 本周产出

- `notes/week-00.md`
- 环境版本清单：Python、Poetry、LangChain、Chatchat、模型服务。
- 一张“Chatchat 与模型服务”的进程和端口图。
- 保存 3 个请求：普通对话、Embedding、知识库问答。

### 验收

- [ ] 能解释为什么 Chatchat 和 Xinference/Ollama 应分开。
- [ ] 能指出配置和数据实际保存在哪里。
- [ ] `7861/docs` 和 `8501` 都能访问。
- [ ] 能通过 API 获得普通对话结果。
- [ ] 能从 samples 知识库召回至少一个文档片段。

---

## 第 1 周：Python 异步、CLI、配置与进程架构

**时间：8 小时**

### 目标

- 补齐阅读本项目需要的 Python 特性。
- 看懂 `chatchat start -a` 的启动过程。
- 看懂 YAML 配置如何变成 `Settings` 对象。

### 必要概念

- 类型注解、Pydantic Model。
- 生成器与异步生成器。
- `async`/`await`、Task、Semaphore。
- Context Manager 与 `asynccontextmanager`。
- Python `multiprocessing.Process/Event/Manager`。
- 装饰器基本原理。

不需要重新学习完整 Python，只针对源码中出现的语法写最小示例。

### 阅读顺序

1. [`cli.py`](../../libs/chatchat-server/chatchat/cli.py)
2. [`startup.py`](../../libs/chatchat-server/chatchat/startup.py)
3. [`settings.py`](../../libs/chatchat-server/chatchat/settings.py)
4. [`pydantic_settings_file.py`](../../libs/chatchat-server/chatchat/pydantic_settings_file.py)
5. [`server_app.py`](../../libs/chatchat-server/chatchat/server/api_server/server_app.py)

### 每日任务

| 天 | 任务 |
|---|---|
| 1 | 阅读 CLI，画出 `init/kb/start` 三个命令入口 |
| 2 | 阅读 `start_main_server`，标出 API/WebUI 两个进程 |
| 3 | 阅读 `run_api_server`、`run_webui`，找到端口来源 |
| 4 | 修改学习目录中的一个无风险配置并验证加载 |
| 5 | 为启动链路加入临时断点或日志，验证执行顺序后撤销 |

### 实验

分别运行：

```bash
poetry run python chatchat/cli.py start --api
poetry run python chatchat/cli.py start --webui
poetry run python chatchat/cli.py start -a
```

观察进程、端口和父子关系：

```bash
ps -ef --forest | rg 'chatchat|streamlit|uvicorn'
ss -ltnp | rg '7861|8501'
```

### 本周产出

- 启动调用链图。
- 一张配置文件到 `Settings` 属性的映射表。
- 解释为什么 WebUI 和 API 使用独立进程。

### 验收问题

1. `CHATCHAT_ROOT` 在 import 时还是请求时读取？
2. `-a` 在哪里转换为 `api=True`、`webui=True`？
3. `Event` 在启动顺序中发挥什么作用？
4. 哪些配置修改可以热加载，哪些需要重启？

---

## 第 2 周：FastAPI、OpenAI 兼容接口与流式输出

**时间：8～10 小时**

### 目标

- 看懂路由注册、Pydantic Schema 和模型 Client 构建。
- 理解普通 JSON 响应与 SSE 流式响应。
- 追踪一次普通对话直到外部模型服务。

### 阅读顺序

1. [`server_app.py`](../../libs/chatchat-server/chatchat/server/api_server/server_app.py)
2. [`api_schemas.py`](../../libs/chatchat-server/chatchat/server/api_server/api_schemas.py)
3. [`chat_routes.py`](../../libs/chatchat-server/chatchat/server/api_server/chat_routes.py)
4. [`openai_routes.py`](../../libs/chatchat-server/chatchat/server/api_server/openai_routes.py)
5. [`server/utils.py`](../../libs/chatchat-server/chatchat/server/utils.py) 中 `get_OpenAIClient` 等函数

### 要回答的调用链

```text
POST /chat/chat/completions
→ OpenAIChatInput
→ chat_completions
→ get_OpenAIClient
→ AsyncClient.chat.completions.create
→ 模型服务
→ EventSourceResponse
```

### 实验

1. 使用 curl 分别发送 `stream=false` 和 `stream=true` 请求。
2. 使用 `curl -N` 观察 SSE 数据分块。
3. 故意使用不存在的模型名，记录错误在哪一层出现。
4. 临时降低某个平台的并发配置，用并发请求观察 Semaphore。
5. 阅读并运行相关测试：

```bash
cd libs/chatchat-server
poetry run pytest tests/api/test_openai_wrap.py -q
```

测试需要外部模型时，先阅读 Fixture；不要为了“全绿”盲目修改代码。

### 本周产出

- 普通聊天调用链。
- 一份 SSE 帧示例，标注 `data`、结束事件和异常事件。
- 模型平台选择与并发控制说明。

### 验收问题

1. `/v1/chat/completions` 与 `/chat/chat/completions` 的职责有什么不同？
2. `get_model_client()` 为什么使用 Semaphore？
3. 客户端断开流式连接时，服务端如何处理？
4. OpenAI 兼容层给模型替换带来什么好处？

---

## 第 3 周：文档加载、分块与知识入库

**时间：9～10 小时**

### 目标

- 完整理解“原始文件变成向量”的链路。
- 理解 Chunk、Overlap、Metadata 和 Document ID。
- 比较至少两种分块策略。

### 阅读顺序

1. `server/knowledge_base/kb_doc_api.py`
2. `server/knowledge_base/utils.py` 中 `KnowledgeFile`
3. `server/file_rag/document_loaders`
4. `server/file_rag/text_splitter`
5. `server/knowledge_base/kb_service/base.py`
6. `server/knowledge_base/kb_service/faiss_kb_service.py`
7. `server/db/models/knowledge_*`
8. `server/db/repository/knowledge_*`

### 必要概念

- LangChain `Document(page_content, metadata)`。
- Loader 与 TextSplitter 的职责边界。
- Embedding 的输入批次与向量维度。
- 原始文件、Chunk、向量 ID 和数据库记录的映射。
- OCR 只在什么情况下启用。

### 实验

准备一份结构清晰、你熟悉答案的 Markdown 文档，至少包含：

- 一级和二级标题。
- 一段很长的连续文本。
- 表格或列表。
- 两个相似但不同的术语。

分别设置：

```text
实验 A：CHUNK_SIZE=300, OVERLAP_SIZE=50
实验 B：CHUNK_SIZE=750, OVERLAP_SIZE=150
实验 C：CHUNK_SIZE=1200, OVERLAP_SIZE=200
```

记录：

- Chunk 数量。
- 边界是否破坏语义。
- Metadata 是否正确。
- 入库时间。
- 后续查询召回情况。

运行分块相关测试：

```bash
poetry run pytest tests/custom_splitter/test_different_splitter.py -q
```

### 本周产出

- RAG 入库数据流图。
- 三组分块实验表格。
- 一份 `Document` 和数据库记录的字段映射。

### 验收问题

1. 为什么原始文件不能直接整体 Embedding？
2. Overlap 太大和太小分别有什么问题？
3. 文档内容和向量元数据分别保存在哪里？
4. 更换 Embedding 模型后为什么通常需要重建向量库？

---

## 第 4 周：混合检索、重排与 RAG 生成

**时间：10 小时**

### 目标

- 看懂 FAISS + BM25 混合检索。
- 理解 Top K、Score Threshold 和 Reranker。
- 追踪 `/chat/kb_chat` 的完整生成链路。
- 初步建立 RAG 评测意识。

### 阅读顺序

1. [`kb_chat.py`](../../libs/chatchat-server/chatchat/server/chat/kb_chat.py)
2. `kb_service/base.py::search_docs`
3. `faiss_kb_service.py::do_search`
4. [`ensemble.py`](../../libs/chatchat-server/chatchat/server/file_rag/retrievers/ensemble.py)
5. [`reranker.py`](../../libs/chatchat-server/chatchat/server/reranker/reranker.py)
6. Prompt 配置中的知识库模板

### 实验矩阵

固定 10 个问题，至少包含：

- 精确关键词问题 3 个。
- 同义表达问题 3 个。
- 跨 Chunk 问题 2 个。
- 知识库中没有答案的问题 2 个。

对比：

| 变量 | 取值建议 |
|---|---|
| Top K | 1、3、5 |
| Score Threshold | 严格、中等、放宽 |
| 检索器 | 纯向量、纯 BM25、0.5/0.5 混合 |
| Reranker | 关闭、开启 |

如果不想立即修改生产代码，可以先复制 `EnsembleRetrieverService` 的最小逻辑到实验脚本中。

运行 FAISS 测试：

```bash
poetry run pytest tests/kb_vector_db/test_faiss_kb.py -q
```

### 失败分类

每个错误答案必须归到一类：

```text
解析失败
分块失败
Embedding 不匹配
召回失败
排序失败
Prompt 丢失约束
LLM 忽略证据
问题本身无答案
```

### 本周产出

- RAG 查询调用链。
- 10 问 × 多组参数的结果表。
- 对 3 个失败案例做根因分析。

### 验收问题

1. BM25 和向量检索分别擅长什么？
2. 为什么 Top K 不是越大越好？
3. Reranker 位于召回前还是召回后？
4. 检索命中但答案错误时，应先检查哪几层？

---

## 第 5 周：数据库、知识库 API 与 WebUI

**时间：8 小时**

### 目标

- 理解文件系统、FAISS、SQLite 三种持久化的边界。
- 看懂知识库 CRUD API。
- 了解 Streamlit 如何调用 FastAPI；不深挖样式。

### 阅读顺序

1. `server/db/base.py`、`session.py`
2. `server/db/models/knowledge_base_model.py`
3. `server/db/models/knowledge_file_model.py`
4. 对应的 Repository
5. `api_server/kb_routes.py`
6. `knowledge_base/kb_api.py`、`kb_doc_api.py`
7. `webui_pages/knowledge_base/knowledge_base.py`

### 实验

使用 API 完成完整生命周期：

```text
创建知识库
→ 上传文件
→ 列出文件
→ 搜索文档
→ 更新文档
→ 删除文档
→ 删除知识库
```

参考：

```bash
poetry run pytest tests/api/test_kb_api_request.py -q
```

同时使用 SQLite CLI 检查数据：

```bash
sqlite3 "$CHATCHAT_ROOT/data/knowledge_base/info.db" '.tables'
sqlite3 "$CHATCHAT_ROOT/data/knowledge_base/info.db" '.schema knowledge_base'
```

### 本周产出

- 一张三类存储的关系图。
- 知识库 CRUD 接口清单。
- 一份从 WebUI 按钮到 API 的调用映射。

### 验收问题

1. 删除数据库记录是否自动删除 FAISS 文件？在哪里协调？
2. Repository 模式解决了什么问题？
3. WebUI 为什么不直接操作数据库？
4. 哪些测试会破坏数据，应该使用哪个 `CHATCHAT_ROOT`？

---

## 第 6 周：Agent 基础与执行循环

**时间：10 小时**

### 目标

- 理解 Tool Calling 与 Agent 循环的区别。
- 看懂 AgentExecutor 如何执行、回传 Observation 并终止。
- 能手工模拟两轮 Agent 执行。

### 先掌握概念

```text
Tool：可调用能力及其 Schema
Agent：根据上下文选择下一步行动的策略
AgentExecutor：驱动 Agent 与 Tool 循环的运行器
AgentAction：工具名 + 工具参数
Observation：工具执行结果
intermediate_steps：历史 Action/Observation
AgentFinish：最终答案和终止信号
```

### 阅读顺序

1. `server/agent/tools_factory/calculate.py`
2. `server/agent/tools_factory/tools_registry.py`
3. `server/agents_registry/agents_registry.py`
4. `langchain_chatchat/agents/structured_chat/structured_chat_agent.py`
5. `langchain_chatchat/agents/output_parsers`
6. [`all_tools_agent.py`](../../libs/chatchat-server/langchain_chatchat/agents/all_tools_agent.py)
7. `callbacks/agent_callback_handler.py`

### 手工推演

问题：

```text
请计算 (123 + 77) * 8，并说明结果。
```

手工写出：

```text
Input
→ AgentAction(tool="calculate", tool_input={...})
→ Observation("1600")
→ intermediate_steps
→ AgentFinish("结果是 1600")
```

然后用真实 Agent 请求验证工具名称、参数和 Observation 是否一致。

### 源码实验

在学习分支临时添加结构化日志，记录：

- iteration。
- Action 类型。
- Tool name。
- Tool input。
- Observation 长度。
- 是否触发 AgentFinish。

完成观察后，将无价值的临时日志撤销；有价值的调试代码可以保留在个人实验提交。

### 本周产出

- Agent 主循环图。
- 一次成功工具调用和一次错误工具调用的完整事件序列。
- 对同步 `_call` 与异步 `_acall` 的差异说明。

### 验收问题

1. 工具函数和 Agent 有什么本质区别？
2. `intermediate_steps` 为什么必须回传给模型？
3. Agent 通过什么信号结束？
4. 如何避免 Agent 无限循环？
5. 工具报错时 Observation 应该包含什么，不应该包含什么？

---

## 第 7 周：工具设计与第一次二次开发

**时间：10 小时**

### 目标

- 新增一个安全、可测试的自定义工具。
- 理解工具描述和参数 Schema 对模型选择的影响。
- 覆盖正确调用、不应调用、参数错误和执行异常。

### 阅读样例

按复杂度从低到高：

1. `calculate.py`
2. `weather_check.py`
3. `search_local_knowledgebase.py`
4. `url_reader.py`
5. `text2sql.py`

### 开发任务

实现“文本统计工具”，建议文件：

```text
chatchat/server/agent/tools_factory/text_statistics.py
```

输入：

- `text: str`
- `include_whitespace: bool = False`

输出：

- 字符数。
- 非空白字符数。
- 行数。
- 单词/中文片段的近似数量。

要求：

- 使用 `@regist_tool`。
- 参数用 Pydantic Field 写清楚含义。
- 工具描述明确说明“什么时候应该使用”和“什么时候不应该使用”。
- 不执行 Shell，不访问网络，不读取任意文件。
- 错误返回结构化、可供模型理解的信息。
- 添加单元测试。

详细步骤见[实验与结业项目](./03-exercises-and-capstone.md#实验-5新增文本统计工具)。

### 对照实验

准备三类 Prompt：

1. 明确应该调用工具。
2. 明确不应该调用工具。
3. 容易和其他工具混淆。

分别调整工具 `description`，记录调用准确率。由此理解工具描述不是 UI 文案，而是 Agent 路由规则的一部分。

### 本周产出

- 自定义工具实现。
- 至少 6 个单元测试。
- 10 条工具选择评测。
- 一次独立 Git commit。

### 验收

- [ ] 工具可以通过 API 直接调用。
- [ ] Agent 能在合适问题上选择它。
- [ ] Agent 在普通问答中不会无故调用它。
- [ ] 参数非法时有明确错误。
- [ ] 测试不依赖网络和模型服务。

---

## 第 8 周：MCP、测试策略与可观测性

**时间：8～10 小时**

### 目标

- 理解本地 Tool 与 MCP Tool 的共同点和区别。
- 跑通项目自带的最小 MCP Server 测试。
- 建立单元测试、集成测试、端到端测试分层。

### 阅读顺序

1. `agent_toolkits/mcp_kit/client.py`
2. `agent_toolkits/mcp_kit/tools.py`
3. `agent_toolkits/mcp_kit/prompts.py`
4. `api_server/mcp_routes.py`
5. `db/models/mcp_connection_model.py`
6. `tests/integration_tests/mcp_platform_tools/math_server.py`
7. `tests/integration_tests/mcp_platform_tools/test_mcp_platform_tools.py`

### 测试分层

```text
单元测试
  不连接模型、网络和外部数据库
  测纯函数、Schema、解析器、工具

集成测试
  连接一个真实模型/MCP/向量库
  测模块协作

端到端测试
  从 API/WebUI 到模型和数据层
  测完整用户行为
```

### 实验

1. 运行无需模型的 MCP Prompt 单测：

```bash
poetry run pytest tests/unit_tests/test_mcp_prompts.py -q
```

2. 阅读数学 MCP Server，列出 stdio 通信边界。
3. 跑通一个 MCP 工具调用，记录 `server_name` 和 `tool name` 如何共同定位工具。
4. 模拟 MCP Server 不可达、超时和返回非法数据。

### 可观测性清单

为 Agent/RAG 调试至少记录：

- request/conversation ID。
- 选择的模型平台。
- 检索耗时和召回数量。
- Prompt 上下文长度。
- Agent iteration。
- Tool name/input/duration/result status。
- 最终终止原因。

不要记录 API Key、用户敏感原文或完整隐私文档。

### 本周产出

- 本地工具与 MCP 工具对比表。
- 测试金字塔。
- 一份 Agent/RAG 调试字段规范。

### 验收问题

1. 为什么 MCP Tool 需要 `server_name`？
2. MCP 故障应该中断整个 Agent，还是作为 Observation 返回？
3. 哪些行为可以在无模型条件下做单元测试？
4. 如何避免日志泄露密钥和知识库内容？

---

## 第 9 周：结业项目实现

**时间：10～12 小时**

### 推荐项目

实现一个“Langchain-Chatchat 源码学习助手”：

- 知识库内容：本仓库 README、开发文档、你前八周的学习笔记。
- RAG：回答项目架构和源码位置问题，并返回引用。
- 自定义工具：文本统计工具。
- 第二个工具：源码路径解释工具，只允许访问预定义路径映射，不允许任意文件读取。
- Agent：根据问题选择知识库或工具。
- API：通过 OpenAI 兼容 Chat Completions 调用。
- 评测：至少 20 条固定问题。

### 实现顺序

1. 定义范围和成功标准。
2. 整理知识文档并设计 Chunk。
3. 建立 FAISS 知识库。
4. 先验证纯 RAG。
5. 接入自定义工具。
6. 再启用 Agent 路由。
7. 添加错误处理和超时。
8. 编写测试和运行说明。

不要从 Agent 开始。先确保知识库检索本身可靠，再让 Agent 决定是否检索。

### 本周产出

- 可运行项目。
- README：架构、配置、启动、测试。
- 20 条评测集初稿。
- 已知限制列表。

---

## 第 10 周：评测、优化与源码复盘

**时间：8～10 小时**

### 目标

- 用固定数据而不是主观感受评价系统。
- 完成一次从失败案例出发的优化。
- 能独立讲解整个系统。

### 评测维度

| 维度 | 指标示例 |
|---|---|
| 检索 | Recall@K、相关文档是否进入候选 |
| 引用 | 引用是否存在、是否支持答案 |
| 回答 | 正确性、完整性、拒答能力 |
| Agent 路由 | 应调用时调用、不应调用时不调用 |
| 工具参数 | 字段和类型是否正确 |
| 稳定性 | 超时、无结果、异常能否处理 |
| 性能 | 首 Token 时间、总耗时、检索耗时 |

### 优化闭环

```text
固定失败案例
→ 判断失败层
→ 只修改一个变量
→ 重跑完整评测
→ 比较改善与回归
→ 记录结论
```

一次只修改一个变量，例如：

- Chunk Size。
- Top K。
- 混合检索权重。
- 工具描述。
- Agent 最大迭代次数。
- Prompt 中的拒答约束。

### 最终复述

不看笔记，完整讲解：

1. 系统启动过程。
2. 普通对话链路。
3. 文档入库链路。
4. RAG 查询链路。
5. Agent 工具循环。
6. MCP 工具链路。
7. 三类数据如何存储。
8. 最常见的五类失败及排查方法。

### 最终验收

- [ ] 完成 20 条以上评测并保存结果。
- [ ] 至少修复或改善一个真实失败案例。
- [ ] 自定义工具有测试。
- [ ] 项目可以由另一个开发者按照 README 启动。
- [ ] 能在 15 分钟内画出完整架构和关键调用链。

## 计划结束后的三个方向

完成主线后再选择一个方向深入：

### RAG 工程方向

- Query Rewrite。
- 多路召回与可学习融合。
- Reranker。
- Parent/Child Chunk。
- RAG 自动评测。

### Agent 工程方向

- LangGraph 或状态机式 Agent。
- Tool 权限、确认和沙箱。
- 长任务恢复。
- MCP Server 开发。
- Agent 轨迹评测。

### 平台工程方向

- API 鉴权和限流。
- 任务队列。
- 可观测性与成本统计。
- 多租户数据隔离。
- 容器化和 GPU 服务编排。

不要同时选择三个方向。根据结业项目中最感兴趣、问题最多的部分选择一个。
