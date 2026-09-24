# 学习进度清单

开始日期：`____-__-__`  
计划完成日期：`____-__-__`  
当前学习分支：`____________________`

## 第 0 周：环境与运行

- [ ] 建立 Python 3.11 独立环境
- [ ] 安装 Poetry 和服务包依赖
- [ ] 设置独立 `CHATCHAT_ROOT`
- [ ] 准备 Chat LLM 和 Embedding 服务
- [ ] 完成 `chatchat init`
- [ ] 完成 `chatchat kb -r`
- [ ] API 与 WebUI 启动成功
- [ ] 普通对话成功
- [ ] samples 知识库问答成功
- [ ] 完成 week-00 学习日志

## 第 1 周：启动与配置

- [ ] 读完 `cli.py`
- [ ] 读完 `startup.py` 主链路
- [ ] 读完 `settings.py` 关键配置类
- [ ] 画出启动进程图
- [ ] 完成端口修改实验
- [ ] 能回答本周四个验收问题

## 第 2 周：API 与流式输出

- [x] 找到全部 Router 注册位置
- [x] 追踪一次普通聊天调用链
- [x] 完成 stream true/false 对比
- [x] 记录一次 SSE 事件序列
- [x] 理解模型平台选择和 Semaphore
- [x] 完成 week-02 学习日志

> 验收说明：非流式请求、SSE 流式请求和客户端中断均已手工验证。自动化用例因测试进程未加载当前 `CHATCHAT_ROOT`而暂缓，不记录为 pytest 通过。

## 第 3 周：RAG 入库

- [x] 追踪上传文件到 Loader
- [x] 追踪 Loader 到 TextSplitter
- [x] 追踪 Document 到 Embedding
- [x] 追踪向量和元数据存储
- [x] 完成三组 Chunk 参数实验
- [x] 画出入库数据流图

> 验收说明：已完成原文件到 Loader、TextSplitter、BGE-M3、FAISS 和 SQLite 的完整调用链；已使用 `300/50`、`750/150`、`1200/200` 对同一文档进行内存分块和纯 FAISS 召回对比，四个验收问题已完成。学习日志见 `notes/第3周-文档加载分块与知识入库.md`。

## 第 4 周：RAG 查询

- [ ] 追踪 `/chat/kb_chat`
- [ ] 理解 FAISS Retriever
- [ ] 理解 BM25 Retriever
- [ ] 理解 Ensemble 权重
- [ ] 理解 Reranker 所在位置
- [ ] 完成至少 10 个问题的参数实验
- [ ] 分析至少 3 个失败案例

## 第 5 周：数据与 WebUI

- [ ] 理解 SQLAlchemy Model/Repository/Session
- [ ] 完成知识库 CRUD API 实验
- [ ] 查看 SQLite 表和关键字段
- [ ] 映射 WebUI 按钮到 API
- [ ] 画出文件/FAISS/SQLite 关系图

## 第 6 周：Agent 循环

- [ ] 理解 Tool Schema
- [ ] 理解 AgentAction
- [ ] 理解 Observation
- [ ] 理解 intermediate_steps
- [ ] 理解 AgentFinish
- [ ] 追踪 `_acall` 主循环
- [ ] 记录成功与失败工具调用轨迹
- [ ] 画出 Agent 状态图

## 第 7 周：自定义工具

- [ ] 实现 `text_statistics`
- [ ] 添加参数 Schema 和 Description
- [ ] 添加至少 6 个单元测试
- [ ] 通过直接 Tool API 调用
- [ ] 通过 Agent 自动调用
- [ ] 完成 10 条工具选择评测
- [ ] 创建独立 Git commit

## 第 8 周：MCP 与测试

- [ ] 阅读 MCP Client
- [ ] 阅读 MCP Tool 包装
- [ ] 运行 MCP Prompt 单测
- [ ] 跑通最小 MCP Server
- [ ] 模拟 MCP 异常
- [ ] 完成测试金字塔
- [ ] 完成日志字段规范

## 第 9 周：结业项目

- [ ] 建立源码学习知识库
- [ ] 纯 RAG 问答可用
- [ ] 接入 3 个限制工具
- [ ] Agent 路由可用
- [ ] 错误和超时处理完成
- [ ] 20 条评测集初稿完成
- [ ] 项目 README 完成

## 第 10 周：评测与复盘

- [ ] 完成 20 条以上评测
- [ ] 完成失败分类
- [ ] 只修改一个变量完成优化
- [ ] 检查优化是否引入回归
- [ ] 完成最终架构图
- [ ] 完成 15 分钟结业演示
- [ ] 选定后续深入方向

## 阶段复盘

### 我现在能独立完成什么

- 

### 我仍然说不清楚什么

- 

### 最值得保留的三个实验

1. 
2. 
3. 

### 下一阶段方向

- [ ] RAG 工程
- [ ] Agent 工程
- [ ] 平台工程
