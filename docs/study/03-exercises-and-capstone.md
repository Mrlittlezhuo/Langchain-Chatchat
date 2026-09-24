# 实验、练习与结业项目

## 1. 实验通用规则

所有实验遵守以下规则：

1. 使用独立学习分支。
2. 使用独立 `CHATCHAT_ROOT`。
3. 每次只改变一个变量。
4. 命令、输入、输出和结论必须写入学习日志。
5. 修改前先构造能够复现当前行为的请求或测试。
6. 不把真实 API Key、隐私文档和访问 Token 提交到 Git。

建议准备目录：

```bash
cd /home/lab239/chenzhuo/Langchain-Chatchat
git switch -c study/langchain-chatchat
mkdir -p docs/study/notes docs/study/results
```

个人运行数据放在仓库外：

```bash
export CHATCHAT_ROOT=/home/lab239/chenzhuo/chatchat-study-data
```

## 实验 1：启动进程与配置追踪

### 目的

理解 CLI、父进程、API 子进程、WebUI 子进程和 YAML 配置的关系。

### 步骤

1. 只启动 API：

```bash
cd libs/chatchat-server
poetry run python chatchat/cli.py start --api
```

2. 在另一个终端观察：

```bash
ps -ef --forest | rg 'chatchat|uvicorn|streamlit'
ss -ltnp | rg '7861|8501'
```

3. 停止后只启动 WebUI，再观察一次。
4. 最后使用 `-a` 同时启动。
5. 将 `basic_settings.yaml` 中 API 端口临时改为 `17861`，验证端口来源，再恢复。

### 需要记录

- 每种启动方式的进程树。
- 哪个进程监听哪个端口。
- 配置修改是否需要重启。
- Ctrl+C 后是否残留子进程。

### 验收

能够在不看代码的情况下画出：

```text
Click → start_main_server → Process → API/WebUI
```

## 实验 2：SSE 流式响应

### 目的

理解流式输出不是“一次返回一个长 JSON”，而是持续发送事件。

### 步骤

从 Swagger 获取当前请求 Schema，分别构造非流式和流式请求。流式请求使用：

```bash
curl -N http://127.0.0.1:7861/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "<你的模型 ID>",
    "messages": [{"role": "user", "content": "用三点解释 RAG"}],
    "stream": true
  }'
```

再用 Python 写一个最小客户端，逐行打印事件到达时间。

### 观察项

- 首个事件耗时。
- 每个 Chunk 的结构。
- 最终结束标志。
- 客户端中途 Ctrl+C 后服务端日志。
- 模型服务不可达时的错误格式。

### 验收

能解释 `AsyncGenerator`、`EventSourceResponse` 和模型 SDK Stream 之间的关系。

## 实验 3：分块参数对比

### 目的

用数据理解 Chunk Size 和 Overlap，不靠经验背参数。

### 测试文档

自己写一份 2000～4000 字 Markdown 文档，包含：

- 多级标题。
- 事实列表。
- 两个相似概念。
- 一个答案跨段落的问题。
- 一个文档中不存在答案的问题。

### 参数组

| 组 | Chunk Size | Overlap |
|---|---:|---:|
| A | 300 | 50 |
| B | 750 | 150 |
| C | 1200 | 200 |

### 记录模板

| 参数组 | Chunk 数 | 边界完整性 | 入库耗时 | Recall@3 | 回答正确数 |
|---|---:|---|---:|---:|---:|
| A | | | | | |
| B | | | | | |
| C | | | | | |

### 验收

能够根据文档类型解释为什么选择某组参数，而不是简单说“默认值最好”。

## 实验 4：FAISS、BM25 与混合检索

### 目的

理解语义检索和关键词检索的互补关系。

### 准备问题

- 包含精确产品名、错误码、函数名的问题。
- 不包含原文关键词但语义相同的问题。
- 同义词问题。
- 文档中不存在答案的问题。

### 对比

在实验脚本中分别运行：

1. FAISS Retriever。
2. BM25 Retriever。
3. 权重 `0.5/0.5` 的 EnsembleRetriever。
4. 权重 `0.8/0.2`。
5. 权重 `0.2/0.8`。

项目实现参考：

```text
libs/chatchat-server/chatchat/server/file_rag/retrievers/ensemble.py
```

### 记录模板

| Query | 应命中文档 | FAISS 排名 | BM25 排名 | 混合排名 | 结论 |
|---|---|---:|---:|---:|---|
| | | | | | |

### 验收

能举出至少一个 BM25 胜出和一个向量检索胜出的真实例子。

## 实验 5：新增文本统计工具

### 目的

完成第一次 Agent 二次开发，同时把工具逻辑保持为可离线单测的纯函数。

### 建议位置

```text
libs/chatchat-server/chatchat/server/agent/tools_factory/text_statistics.py
```

### 功能规格

输入：

```text
text: string，必填，需要统计的文本
include_whitespace: boolean，可选，默认 false
```

输出建议：

```json
{
  "characters": 12,
  "characters_without_whitespace": 10,
  "lines": 2,
  "tokens_approx": 6
}
```

### 设计要求

1. 使用 `@regist_tool` 注册。
2. 工具名保持稳定、语义清晰。
3. Description 必须说明适用场景。
4. 参数通过 Pydantic Field 描述。
5. 空字符串有明确定义。
6. 不访问网络和文件系统。
7. 超长文本设置合理限制或给出明确行为。
8. 返回 `BaseToolOutput` 或与现有工具一致的格式。

### 测试用例

至少覆盖：

```text
空字符串
纯中文
纯英文
中英混合
包含换行和制表符
包含 emoji
include_whitespace=true/false
非法参数类型
```

建议新增测试：

```text
libs/chatchat-server/tests/unit_tests/test_text_statistics_tool.py
```

运行：

```bash
cd libs/chatchat-server
poetry run pytest tests/unit_tests/test_text_statistics_tool.py -q
```

### Agent 选择评测

应该调用：

- “统计下面内容有多少字符和多少行……”
- “这段文本去掉空白后多长？”

不应该调用：

- “帮我总结这段文本。”
- “解释 Python 中 len 的作用。”
- “计算 12 × 9。”

模糊场景：

- “看看这段文本的基本情况。”
- “这段文案是不是太长？”

记录 Tool Description 调整前后的选择结果。

## 实验 6：Agent 循环观测

### 目的

将 Agent 从黑盒变成可以观察的状态机。

### 观测字段

对每轮执行记录：

```text
iteration
elapsed_time
action_type
tool_name
tool_input
observation_type
observation_length
finish_reason
```

### 请求集合

1. 只需一次工具调用的问题。
2. 需要先知识库搜索再计算的问题。
3. 工具名不存在的问题。
4. 工具参数缺失的问题。
5. 工具执行抛异常的问题。
6. 无需工具的普通问答。

### 安全要求

- 不记录 API Key。
- 不记录完整隐私文本。
- Tool Input 过长时截断并标记。
- Observation 记录状态和摘要，而不是无上限原文。

### 验收

能用一次真实 Trace 解释：

```text
AgentAction → Tool → Observation → intermediate_steps → AgentFinish
```

## 实验 7：MCP 最小闭环

### 目的

理解 MCP 不是另一种 Agent，而是标准化工具提供协议。

### 推荐入口

```text
tests/integration_tests/mcp_platform_tools/math_server.py
tests/integration_tests/mcp_platform_tools/test_mcp_platform_tools.py
langchain_chatchat/agent_toolkits/mcp_kit/client.py
langchain_chatchat/agent_toolkits/mcp_kit/tools.py
```

### 步骤

1. 阅读数学 MCP Server 暴露的工具 Schema。
2. 画出 stdio 进程关系。
3. 运行对应集成测试。
4. 记录 MCP tool 转换为 LangChain Tool 的字段映射。
5. 故意修改工具名造成不匹配，观察错误如何进入 Observation。

### 对比表

| 维度 | 本地 `@regist_tool` | MCP Tool |
|---|---|---|
| 代码位置 | Chatchat 进程内 | 外部 MCP Server |
| 发现方式 | Import 时注册 | 协议列举工具 |
| 调用边界 | Python 函数 | stdio/SSE/协议调用 |
| 故障类型 | 函数异常 | 连接、协议、远端异常 |
| 权限边界 | 与应用一致 | 可独立隔离 |

## 结业项目：源码学习 Agent

## 1. 项目目标

构建一个专门回答当前 Langchain-Chatchat 仓库问题的 Agent。它必须能够：

- 回答项目架构和运行方式。
- 根据问题检索源码学习文档。
- 返回支持答案的引用。
- 在需要文本统计时调用自定义工具。
- 在知识库没有依据时明确拒答或说明不确定。
- 输出可观察的工具执行轨迹。

## 2. 知识库范围

第一版只导入：

```text
README.md
docs/contributing/README_dev.md
docs/study/*.md
libs/chatchat-server/README.md
```

不要第一版就把整个仓库所有 Python 文件导入。先保证高质量小范围知识库，再逐步增加源码摘要。

第二版可以加入你自己编写的源码卡片，例如：

```text
source-notes/
├── startup.md
├── api-routing.md
├── rag-ingestion.md
├── rag-query.md
├── agent-loop.md
└── mcp.md
```

每张源码卡片包含：

- 功能。
- 入口文件。
- 关键函数。
- 输入输出。
- 调用链。
- 已知限制。

## 3. Agent 工具

第一版只允许三个工具：

1. `search_local_knowledgebase`
2. `text_statistics`
3. `calculate`

限制工具数量可以更清楚地评测路由能力。

第二版再考虑 MCP 工具或源码路径查询工具。

## 4. 评测集

至少包含 20 条：

| 类型 | 数量 | 示例 |
|---|---:|---|
| 架构事实 | 5 | API Server 从哪里创建？ |
| RAG 链路 | 4 | 混合 Retriever 如何构造？ |
| Agent 链路 | 4 | Observation 在哪里重新加入循环？ |
| 工具调用 | 3 | 统计一段文本长度 |
| 无需工具 | 2 | 用一句话解释 Embedding |
| 无答案/越界 | 2 | 询问仓库完全未包含的信息 |

评测结果表：

| ID | 问题 | 预期工具 | 实际工具 | 检索命中 | 回答正确 | 引用正确 | 耗时 | 失败类型 |
|---|---|---|---|---|---|---|---:|---|
| Q01 | | | | | | | | |

## 5. 最低验收标准

- 20 条问题中，工具选择正确率至少 85%。
- 有答案问题的相关文档 Recall@3 至少 85%。
- 无答案问题不能伪造源码路径或函数。
- 每个引用都能在导入文档中找到。
- 工具异常不会导致整个服务无结构崩溃。
- 自定义工具单元测试全部通过。
- README 中包含启动、配置、测试和已知限制。

这些数值不是生产标准，而是让学习成果具有可比较基线。

## 6. 失败分析模板

```markdown
### Case ID

- 问题：
- 期望行为：
- 实际行为：
- 是否选对工具：
- 是否召回正确文档：
- Prompt 是否包含证据：
- LLM 是否使用证据：
- 根因分类：解析/分块/Embedding/召回/排序/Prompt/Agent/Tool/模型
- 本次只修改的变量：
- 修改后结果：
- 是否出现回归：
```

## 7. 结业演示顺序

最终演示控制在 15 分钟：

1. 2 分钟：架构和目标。
2. 3 分钟：知识库入库与检索。
3. 3 分钟：普通 RAG 问答。
4. 3 分钟：Agent 自动选择工具。
5. 2 分钟：失败案例与修复。
6. 2 分钟：测试、限制和下一步。

演示是否漂亮不是重点。能够展示调用证据、失败分析和工程取舍才是完成标志。
