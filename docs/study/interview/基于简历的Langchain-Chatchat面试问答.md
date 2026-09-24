# 基于简历的 Langchain-Chatchat 面试问答

> 整理日期：2026-09-06  
> 项目版本：Langchain-Chatchat `0.3.1.3`  
> Python：`3.10.20`  
> LangChain：`0.1.17`  
> 模型服务：Ollama `0.32.15`  
> LLM：`qwen2:7b`  
> Embedding：`bge-m3`  
> 用途：根据当前简历中的项目描述，准备面试官可能提出的问题和可选择回答的详细内容。

---

## 0. 使用方法与事实边界

每个问题分为两层：

1. **建议回答**：先说这一部分，通常控制在 30～90 秒；
2. **追问补充**：只有面试官继续深挖时再展开，不要第一次回答就把所有源码细节全部倒出来。

本项目在简历中的定位是“个人源码学习和工程实践项目”，不是从零开发了一套新的 RAG 框架。回答时要明确区分：

```text
项目原有能力：Langchain-Chatchat 已经提供的框架和功能
个人完成工作：部署、配置、运行验证、源码追踪、实验、故障定位和小范围修复
尚未完成工作：Reranker 实装、自定义工具开发、MCP 实战、系统化自动评测和生产化改造
```

### 0.1 当前可以有把握地说

- 完成本地源码环境搭建和服务启动；
- 使用 Ollama 接入 `qwen2:7b` 和 `bge-m3`；
- 独立设置 `CHATCHAT_ROOT`，完成源码、模型服务和运行数据隔离；
- 重建 `samples` 知识库，12 个文件生成 755 个文档块；
- 验证普通对话、Embedding、知识库问答、来源链接和流式接口；
- 追踪文档上传、Loader、TextSplitter、Embedding、FAISS 和 SQLite 入库链路；
- 追踪 FAISS、BM25、RRF、Prompt 和 LLM 的知识库查询主链；
- 完成三组分块参数实验；
- 定位检索阈值语义不一致、`score=3.0` 和 BM25 噪声问题；
- 阅读 Agent 的模型决策、工具执行、Observation 回传和事件输出链；
- 修复 WebUI 中 `use_mcp` 未初始化导致的 `UnboundLocalError`。

### 0.2 当前不要说成已经完成

- 不要说已经开发并测试了自定义工具；
- 不要说已经完成 MCP Server 接入；
- 不要说已经启用了 Reranker，当前相关代码是注释状态；
- 不要说已经建立完整 RAG 自动评测集；
- 不要说项目全部 pytest 已通过，当前主要是手工接口和页面验证；
- 不要把修改配置阈值说成已经彻底修复了混合检索设计。

---

## 1. 项目开场与个人贡献

### 问题 1：请用两分钟介绍一下 Langchain-Chatchat 项目

#### 建议回答

> Langchain-Chatchat 是一个面向本地知识库问答和 Agent 应用的开源大模型应用框架。我的工作重点不是只把页面运行起来，而是以源码方式完成部署，并沿着真实请求梳理它的工程调用链。
>
> 整体上，Streamlit WebUI 负责页面交互，FastAPI 负责业务接口，Ollama 负责加载 Qwen2:7B 和 BGE-M3。Qwen2 用于回答生成，BGE-M3 用于把文档块和用户问题转换成 1024 维向量；知识库正文和索引由 FAISS Docstore、FAISS 索引以及 SQLite 共同管理。
>
> 我完成了独立运行环境和数据目录配置，重建了包含 12 个文件、755 个文档块的 samples 知识库，跑通普通对话和 RAG 问答。源码方面，我重点追踪了文档上传、解析、分块、Embedding、FAISS/BM25 混合检索、RRF 排名融合、Prompt 拼装和流式响应链路。我还通过实验定位了默认检索阈值与 LangChain 实际相关度语义不一致的问题：阈值只过滤 FAISS，BM25 会掩盖向量分支失效，同时接口中的 `score=3.0` 只是默认占位值。除此之外，我阅读了 Agent 的多轮模型决策、工具执行和 Observation 回传流程，并修复过一个 WebUI 变量未初始化问题。

#### 追问补充

如果面试官问“这个项目的核心价值是什么”，可以回答：

> 它把模型服务、知识库管理、检索、Prompt、Agent、API 和 WebUI 组合成了完整应用，适合从工程视角理解一个大模型应用，而不是只学习单个 LangChain API。

如果面试官问“你是不是从零实现了 RAG”，要诚实回答：

> 不是从零实现框架。我是在现有项目上完成部署、源码追踪、实验和问题定位，并能够说明每一层的职责、数据形态以及可优化点。

---

### 问题 2：你在这个项目中的个人贡献是什么？

#### 建议回答

> 我的个人工作主要有四部分。第一是环境和模型接入，使用独立 Conda 环境部署源码，配置 Ollama、Qwen2:7B 和 BGE-M3，并通过模型原生接口先验证生成和向量服务。第二是知识库实践，设置独立 `CHATCHAT_ROOT`，完成知识库初始化、文档向量化、普通对话和 RAG 问答。第三是源码分析和实验，我把入库链与查询链追踪到具体函数，并完成分块参数和检索阈值实验。第四是问题排查，包括依赖冲突、配置路径、检索分数异常和 WebUI `use_mcp` 未初始化问题。

#### 追问补充：哪些是代码修改，哪些是配置修改

```text
配置修改：
- 默认 LLM 改为 qwen2:7b；
- 默认 Embedding 改为 bge-m3；
- Ollama 平台地址配置为 127.0.0.1:11434/v1；
- API/WebUI 绑定 0.0.0.0；
- public_host 配置为服务器地址；
- SCORE_THRESHOLD 从 2.0 调整为 0.4。

源码修改：
- 在 WebUI 对话页中给 use_mcp 设置默认值 False，修复未启用 Agent 时引用未赋值局部变量的问题。

分析但尚未实现：
- BM25 停用词与质量过滤；
- RRF 后 Reranker；
- BM25 索引缓存；
- Prompt 引用与注入防御增强。
```

---

### 问题 3：为什么选择研究这个项目，而不是只调用一个大模型 API？

#### 建议回答

> 单独调用模型 API 只能说明模型能生成文本，无法覆盖真实应用中的文档处理、检索、状态管理、流式输出和故障定位。这个项目把 LLM、Embedding、FAISS、BM25、FastAPI、Streamlit、Agent 和数据库组合在一起，可以让我把原有的 Java 后端工程经验与大模型应用结合起来。我更关注的是请求如何穿过系统、数据如何流动、故障边界在哪里，以及怎样通过实验而不是凭感觉优化效果。

---

### 问题 4：这个项目和你原来的 Java 后端经历有什么联系？

#### 建议回答

> 两者的共同点都是服务编排和长耗时任务管理。以前在网络靶场中，我通过 RabbitMQ 把耗时的 OpenStack 资源创建从接口线程中拆出去，并向用户反馈进度；在大模型应用中，Embedding、文档解析和模型生成同样可能耗时，需要考虑异步、任务状态、流式反馈、超时和错误处理。区别是 Langchain-Chatchat 当前主要使用 Python 的事件循环、线程池和 SSE，而 RabbitMQ 是跨进程、跨服务的可靠消息机制。如果把知识库大文件入库生产化，我会考虑把解析和向量化改成消息队列驱动的后台任务。

---

## 2. 环境、配置与服务架构

### 问题 5：你为什么同时使用 Conda 和 Poetry？

#### 建议回答

> Conda 主要负责 Python 解释器版本和环境隔离，Poetry 负责读取项目 `pyproject.toml`、管理 Python 包依赖以及源码包的安装。这个项目声明支持 Python 3.10 到 3.11，但旧版依赖对解释器版本比较敏感，所以我最终在独立 Conda 环境中使用 Python 3.10.20。Poetry 用于理解和安装项目依赖；排障过程中对少量缺失包也使用过 pip，但正式环境应该把依赖变更回写到项目依赖声明和锁文件中，避免环境不可复现。

#### 容易被追问的点

- `pyproject.toml`：项目元数据、依赖、脚本入口和 pytest 配置；
- `poetry.lock`：锁定解析后的具体依赖版本；
- Conda 环境：隔离 Python 和 site-packages；
- 不要说 Conda 和 Poetry 都在重复创建两套同时使用的虚拟环境；实际应明确谁负责解释器、谁负责项目依赖。

---

### 问题 6：为什么最终使用 Python 3.10，而不是原计划的 3.11？

#### 建议回答

> 项目声明范围允许 Python 3.10 和 3.11，但实际锁定的旧版 `pandas` 在 Python 3.11 环境中没有合适的预编译轮子，安装时转为源码构建并失败。因此我没有盲目升级所有依赖，而是先选择项目兼容范围内的 Python 3.10.20，保证源码学习基线能够稳定运行。这个过程说明声明兼容范围不等于每个锁定依赖都在所有版本上有可用构建产物。

---

### 问题 7：`CHATCHAT_ROOT` 是什么？为什么要单独设置？

#### 建议回答

> `CHATCHAT_ROOT` 是 Chatchat 运行配置和数据的根目录。项目在导入 `settings.py` 时通过环境变量读取它；如果没有设置，就使用当前工作目录。我的源码位于 Git 仓库，但配置、日志、SQLite、原始文档和 FAISS 索引放在 `/home/lab239/chenzhuo/chatchat-study-data`。这样更新或修改源码不会覆盖知识库数据，也可以为不同实验准备独立的数据目录。

#### 真实故障

未设置环境变量时，执行配置备份得到：

```text
对 /model_settings.yaml 调用 stat 失败
```

原因是空的 `$CHATCHAT_ROOT` 被 Shell 拼成根目录路径。重新导出正确目录并检查文件后解决。

---

### 问题 8：项目运行时有哪些服务和端口？

#### 建议回答

```text
本地浏览器
  ↓ 10.10.12.248:8501
Streamlit WebUI
  ↓ 10.10.12.248:7861
Chatchat FastAPI
  ├─ FAISS + SQLite：知识库
  └─ 127.0.0.1:11434/v1
       ↓
     Ollama
       ├─ qwen2:7b
       └─ bge-m3
```

> WebUI 使用 8501，API 使用 7861，Ollama 使用 11434。API 和 WebUI 监听 `0.0.0.0`，便于我的本地电脑访问服务器；Ollama 仍只监听 `127.0.0.1`，因为它只需要被服务器上的 Chatchat 调用，没有必要直接暴露模型服务。

---

### 问题 9：`0.0.0.0`、`127.0.0.1` 和 `public_host` 有什么区别？

#### 建议回答

> `0.0.0.0` 是监听所有本机网卡的绑定地址，不能直接当成客户端目标地址；`127.0.0.1` 只允许本机访问；`public_host` 不负责监听，它用于生成外部用户能够访问的 API 或知识库文件链接。我的 API 监听 `0.0.0.0:7861`，而 `public_host` 设置为服务器实际地址 `10.10.12.248`，所以知识库出处链接可以从本地浏览器打开。

---

### 问题 10：执行 `chatchat start -a` 后发生了什么？

#### 建议回答

> `chatchat` 命令由 Click 注册，`start` 子命令进入 `startup.main()`。`-a` 会转换为同时启用 API 和 WebUI。主进程使用 multiprocessing 的 spawn 模式创建两个子进程：API 子进程创建 FastAPI 应用并由 Uvicorn 监听 7861；WebUI 子进程通过 Streamlit bootstrap 运行 `webui.py` 并监听 8501。主进程使用 Event 协调启动顺序，先等待 API 就绪，再启动 WebUI，之后通过 `join()` 监控进程并在退出时清理。

#### 源码主线

```text
chatchat.cli:main
→ chatchat.startup:main
→ start_main_server(args)
→ Process(run_api_server)
→ Process(run_webui)
```

API 子进程：

```text
run_api_server()
→ create_app()
→ include_router()
→ uvicorn.run()
```

---

### 问题 11：配置文件怎样变成 Python 中的 `Settings`？

#### 建议回答

> `settings.py` 在模块导入时确定 `CHATCHAT_ROOT`，然后用 Pydantic Settings 定义 BasicSettings、KBSettings、ApiModelSettings、ToolSettings 和 PromptSettings。每类配置通过 `yaml_file` 指向对应 YAML，`SettingsContainer` 再把它们暴露成统一的 `Settings.basic_settings`、`Settings.kb_settings` 等属性。配置属性通过文件修改时间参与缓存键，在开启自动重载时可以重新构造对象；但已经用于创建监听端口、客户端或其他运行资源的值，不会因为对象重读就自动重建资源，因此 host 和 port 修改后仍需重启服务。

#### 环境变量覆盖

Pydantic 的数据源顺序允许环境变量覆盖 YAML，例如：

```bash
HTTPX_DEFAULT_TIMEOUT=123 python ...
```

实际读取结果为 `123.0`，而不是 YAML 中的 `300.0`。

---

## 3. 模型平台与 OpenAI 兼容接口

### 问题 12：Qwen2 和 BGE-M3 分别负责什么？

#### 建议回答

> Qwen2:7B 是生成模型，负责读取 Prompt、上下文和历史消息并生成答案；BGE-M3 是 Embedding 模型，负责把文档块和查询转换成可以计算距离的向量。它们不能简单互换：生成模型输出 Token 序列，Embedding 模型输出固定长度的数值表示。我的 BGE-M3 实测输出 1024 维向量。

#### 实验依据

```text
知识库应用 vs RAG描述：余弦相似度约0.5597
知识库应用 vs 牛肉面：余弦相似度约0.3592
```

这说明语义更相关的文本在当前模型的向量空间中更接近。

---

### 问题 13：Chatchat 如何根据模型名找到 Ollama？

#### 建议回答

> `model_settings.yaml` 中的 `MODEL_PLATFORMS` 保存平台名称、类型、模型列表、`api_base_url`、`api_key` 和并发数。请求指定 `qwen2:7b` 后，`get_model_info()` 遍历平台配置找到模型所属的 Ollama 平台，`get_OpenAIClient()` 再使用 `http://127.0.0.1:11434/v1` 和 API Key 创建 OpenAI 同步或异步客户端。因为 Ollama 提供 OpenAI 兼容接口，上层业务不需要了解 Ollama 自己的协议细节。

#### 调用链

```text
model_name=qwen2:7b
→ get_config_platforms()
→ get_config_models()
→ get_model_info()
→ get_OpenAIClient()
→ openai.AsyncClient(base_url=Ollama地址)
```

---

### 问题 14：项目为什么同时存在 `/v1/chat/completions` 和 `/chat/chat/completions`？

#### 建议回答

> `/v1/chat/completions` 是模型平台兼容网关，主要负责根据模型名称选择平台，把 OpenAI 风格请求转发到 Ollama、Xinference 或其他兼容服务；`/chat/chat/completions` 是 Chatchat 的业务编排接口，在 OpenAI 风格请求外还处理会话 ID、工具、Agent、MCP、消息入库和项目自定义状态。知识库问答则主要使用 `/chat/kb_chat`。接口名字相似，但职责层级不同。

---

### 问题 15：模型平台中的 Semaphore 有什么作用？

#### 建议回答

> 项目按照 `(model_name, platform_name)` 为每个模型平台组合维护一个 `asyncio.Semaphore`。请求模型前先 `acquire()`，结束后在 `finally` 中 `release()`，用于限制单个模型平台的并发请求，避免过多请求同时进入 GPU 模型服务。等待信号量时使用 `await`，不会让事件循环一直忙等。

#### 不要说错

- Semaphore 控制的是进入模型平台的并发数量，不是创建操作系统进程；
- 它不能替代跨机器负载均衡；
- 当前实现还根据同名模型的平台空闲量进行选择，但不应把它描述成完整的生产级调度系统。

---

### 问题 16：你如何验证模型服务本身正常，而不是直接启动 Chatchat？

#### 建议回答

> 我先在故障边界最小的模型层验证。Qwen2 使用 Ollama `/api/generate`，要求只返回固定句子；BGE-M3 使用 `/api/embed`，检查向量条数和 1024 维输出；然后通过 `ollama ps` 和 `nvidia-smi` 确认模型在 GPU 上运行。模型层正常后再配置 Chatchat，这样如果应用请求失败，可以排除模型未下载、端口未监听或 GPU 未加载等问题。

---

## 4. 文档入库完整链路

### 问题 17：一份文件从上传到可以被检索，完整过程是什么？

#### 建议回答

> 上传请求进入 `/knowledge_base/upload_docs`，`upload_docs()` 先校验知识库并把 UploadFile 保存到对应知识库的 `content` 目录；如果启用向量化，再调用 `update_docs()`。`update_docs()` 为文件创建 `KnowledgeFile`，根据扩展名选择 Loader，将原文件解析成 LangChain Document，再使用 ChineseRecursiveTextSplitter 分块。每个 chunk 的 `page_content` 送给 BGE-M3 生成向量，通过 `FAISS.add_embeddings()` 写入索引；正文和 metadata 保存在 Docstore，同时把文件信息写入 `knowledge_file`，把文件、Document UUID 和 metadata 的关系写入 `file_doc`。

#### 源码调用链

```text
kb_routes.py
→ kb_doc_api.upload_docs()
→ _save_files_in_thread()
→ kb_doc_api.update_docs()
→ files2docs_in_thread()
→ KnowledgeFile.file2text()
→ file2docs()
→ docs2texts()
→ KBService.update_doc()
→ KBService.add_doc()
→ FaissKBService.do_add_doc()
→ embed_documents()
→ FAISS.add_embeddings()
→ add_file_to_db()
→ add_docs_to_db()
```

---

### 问题 18：项目如何根据文件扩展名选择 Loader？

#### 建议回答

> `KnowledgeFile` 初始化时取得扩展名，通过 `LOADER_DICT` 找到对应的 Loader 名称，例如 Markdown 使用 TextLoader、CSV 使用 CSVLoader、PDF 使用 RapidOCRPDFLoader、Excel 使用 UnstructuredExcelLoader。`get_loader()` 再动态导入项目自定义 Loader 或 `langchain_community.document_loaders` 中的 Loader 并实例化。不同 Loader 最终都统一输出 LangChain Document，后面的分块和向量化逻辑就可以复用。

#### 补充细节

- CSV 会使用 chardet 自动识别编码；
- Markdown 当前映射中存在多个候选 Loader，函数按字典遍历顺序返回第一个匹配项；
- 项目自定义 OCR Loader 从 `chatchat.server.file_rag.document_loaders` 导入；
- 加载失败时会尝试回退到 `UnstructuredFileLoader`。

---

### 问题 19：PDF Loader 如何处理文本和图片？

#### 建议回答

> RapidOCRPDFLoader 使用 PyMuPDF 打开 PDF。它先通过 `page.get_text()` 提取 PDF 自带文本层，再遍历页面中的内嵌图片；只有图片宽度和高度相对页面比例都达到 `PDF_OCR_THRESHOLD` 才执行 OCR，当前阈值是 0.6 和 0.6。RapidOCR 的原始结果包含文字区域、文字字符串和置信度，但当前代码只取 `line[1]` 的字符串并追加到全文，最后通过 `partition_text()` 转成文档元素。

#### 如果图中是销售图表

> OCR 可能识别标题、年份、坐标轴、图例和数据标签，但当前代码丢弃坐标和置信度，也不理解柱子、折线和文字之间的空间关系，所以不能可靠得到“销售额连续增长”这样的图表语义。没有文字的图片基本不会贡献内容；矢量图形中的线条和柱子也不会被 OCR 理解。生产方案可以增加视觉语言模型或专门的图表解析步骤。

---

### 问题 20：LangChain Document 中保存什么？

#### 建议回答

> Document 至少包含 `page_content` 和 `metadata`。`page_content` 是 Loader 提取出的正文，`metadata` 保存来源文件等信息。经过 TextSplitter 后仍然是 Document 列表，只是每个 Document 对应一个 chunk。入库前项目会把绝对 source 路径尽量转换为知识库 content 目录下的相对路径，便于知识库迁移和生成下载链接。

### 问题 21：ChineseRecursiveTextSplitter 是怎样分块的？

#### 建议回答

> 它继承 LangChain 的 RecursiveCharacterTextSplitter，按照从粗到细的分隔符递归处理，当前顺序包括双换行、单换行、中文句号问号感叹号、英文句末符号、分号和逗号。先选择当前文本中存在的最高优先级分隔符进行切分；小片段暂存并通过 `_merge_splits()` 合并到接近 `chunk_size`，超过限制的大片段再使用更细的分隔符递归切分。当前默认长度函数本质上按字符长度计算，不是调用 Qwen2 的 tokenizer 计算 Token 数。

#### `keep_separator=True` 的作用

分隔符会跟在前面的文本片段后面，例如句号不会被完全删除，可以保留基本句子边界和可读性。

---

### 问题 22：`chunk_overlap=150` 是否保证相邻块一定重叠 150 个字符？

#### 建议回答

> 不保证。LangChain 合并时保留的是已经切好的完整子片段，它会从当前窗口头部逐段删除，直到剩余长度不大于 overlap，或者新片段能够放入 chunk。它不会机械截取前一块最后 150 个字符。因此实际重叠取决于句子、标点和子片段长度，某些相邻块可能小于 150，甚至没有精确字符串重叠。

#### 为什么这样设计

> 保留完整子片段可以减少从句子中间截断，但代价是 overlap 只能被理解为目标上限或滑动窗口参数，不能理解成严格保证值。

---

### 问题 23：你怎样选择 `chunk_size` 和 `chunk_overlap`？

#### 建议回答

> 我没有只凭经验选择，而是对同一份“大模型推理优化策略”文档做了三组内存实验：`300/50`、`750/150` 和 `1200/200`，比较块数量、长度、实际重叠以及三个问题的纯 FAISS 召回。`300/50` 产生 18 块，主题纯度较高，但 FlashAttention 双概念和两种 Batching 的证据经常分布在 Top1 和 Top2；`750/150` 产生 6 块，三个问题基本都能从 Top1 获得完整证据；`1200/200` 产生 4 块，连续性最好，但单块混入显存优化、调度、量化等更多主题。因此当前保留 `750/150`，它是这份文档和这组问题下的折中，不是通用最优参数。

#### 实验数据

| 参数 | Chunk 数 | 长度范围 | 平均长度 | 平均精确重叠 | 零重叠相邻对 |
|---|---:|---:|---:|---:|---:|
| 300/50 | 18 | 61～290 | 216.7 | 11.1 | 11/17 |
| 750/150 | 6 | 655～740 | 701.8 | 86.2 | 1/5 |
| 1200/200 | 4 | 949～1182 | 1058.5 | 148.3 | 0/3 |

#### 面试中的判断原则

```text
过小：证据被拆散、块数量和索引成本增加、容易漏掉上下文
过大：主题混杂、检索选择性下降、LLM上下文噪声和Token成本增加
Overlap过小：跨边界证据不完整
Overlap过大：相邻向量重复、Top K被相似块占用、存储和计算增加
```

---

### 问题 24：为什么不能把整份长文档直接做一次 Embedding？

#### 建议回答

> 一份长文档通常包含多个主题，而一个固定维度向量需要压缩整篇内容，局部主题会被其他内容稀释。用户问题往往只对应其中一段，整篇向量未必能进入近邻；即使召回整篇，送给 LLM 的上下文也会包含大量无关信息并增加 Token 成本。此外 Embedding 模型通常有输入长度限制，过长文本可能被截断或直接报错。因此需要先把文档切成语义相对集中的 chunk。

---

### 问题 25：为什么更换 Embedding 模型必须重建向量库？

#### 建议回答

> 不同 Embedding 模型可能输出不同维度，维度不同时 FAISS 无法直接比较；即使维度相同，不同模型训练出的每个坐标含义也不同，旧文档向量和新查询向量不在同一语义空间，距离没有意义。因此更换 Embedding 后，必须让所有文档 chunk 使用新模型重新生成向量并重建 FAISS，查询也必须使用同一模型。

---

### 问题 26：`index.faiss`、`index.pkl` 和 SQLite 各自保存什么？

#### 建议回答

```text
content/
→ 原始文件本体

index.faiss
→ 数值向量和FAISS索引结构

index.pkl
→ LangChain Docstore中的chunk正文、metadata，
  以及FAISS位置到Document UUID的映射

knowledge_file
→ 文件名、扩展名、所属知识库、Loader、Splitter、版本、
  修改时间、文件大小、chunk数量、是否自定义docs

file_doc
→ 知识库名、文件名、Document UUID和metadata副本
```

> FAISS 负责向量近邻搜索，Docstore 负责从命中的 ID 取回正文，SQLite 负责知识库和文件的业务管理。它们不是三份完全相同的数据。

#### 真实数据

```text
knowledge_base：1条
knowledge_file：12条
file_doc：755条
index.faiss：约3 MB
index.pkl：约480 KB
```

---

### 问题 27：更新文档时怎样处理旧向量？

#### 建议回答

> `update_docs()` 解析出新 Document 后调用 `kb.update_doc()`；公共服务先删除该文件原有的向量和映射，再调用 `add_doc()` 写入新向量、Docstore 和数据库记录。已有 `knowledge_file` 会更新修改时间、大小、chunk 数量并增加版本号，新文件则创建记录并增加知识库文件数。

#### 回答边界

> 当前实现中 FAISS、磁盘文件和 SQLite 的一致性主要由应用代码维持，不是一个跨存储事务。我已经在源码中观察到重复删除、Session 边界和唯一约束等可研究点，但尚未逐项完成故障注入和修复，所以面试中应把它们描述为“源码观察和后续优化方向”，不能说成已经修复。

---

## 5. 知识库查询、混合检索与 RRF

### 问题 28：用户提出一个知识库问题后，完整调用链是什么？

#### 建议回答

> 请求进入 `POST /chat/kb_chat`。`kb_chat()` 根据 `mode` 和知识库名取得对应服务，检查知识库使用的 Embedding 是否可用，然后通过 `run_in_threadpool()` 调用同步 `search_docs()`。`search_docs()` 通过 KBServiceFactory 找到 FaissKBService，公共 `KBService.search_docs()` 再动态分派到 `FaissKBService.do_search()`。FAISS 服务加载向量库，创建包含 BM25 和 FAISS 的 EnsembleRetriever；两路分别检索后通过 RRF 融合并返回 Document。`kb_chat()` 将正文拼成 context，将来源格式化成下载链接，然后加载 RAG Prompt、调用 Qwen2，并通过 SSE 或完整 JSON 返回答案。

#### 主链路

```text
/chat/kb_chat
→ kb_chat()
→ search_docs()
→ KBServiceFactory.get_service_by_name()
→ KBService.search_docs()
→ FaissKBService.do_search()
→ EnsembleRetrieverService.from_vectorstore()
→ BM25 + FAISS
→ RRF
→ context + question
→ ChatPromptTemplate
→ Qwen2
→ OpenAIChatOutput
```

---

### 问题 29：FAISS 和 BM25 有什么区别？为什么组合使用？

#### 建议回答

> FAISS 保存 BGE-M3 生成的向量，适合处理同义表达和语义相近但字面不同的问题；BM25 根据词频、逆文档频率和文档长度进行关键词排名，适合 `FlashAttention`、`GPTQ` 等专有名词和精确匹配。两者分数体系不同，但能力互补，因此项目先分别召回，再使用 RRF 融合排名。

#### 举例

```text
问题：怎样通过片上存储降低注意力计算的数据搬运？
文档：FlashAttention通过tiling把数据从HBM加载到SRAM……
```

问题和文档的字面词可能不完全一致，FAISS 更有机会凭语义命中。如果问题直接包含 `FlashAttention`，BM25 的精确词匹配通常更稳定。

---

### 问题 30：RRF 是什么？为什么不用原始分数相加？

#### 建议回答

> BM25 分数与向量相关度的定义和数值范围不同，直接相加没有稳定意义。RRF，也就是 Reciprocal Rank Fusion，主要根据文档在各路检索中的名次计算分数。当前 LangChain 默认常量 `c=60`，某个文档在一路中的贡献是 `weight/(rank+c)`；项目给 BM25 和 FAISS 的权重各为 0.5。同一正文同时在两路排名靠前时，贡献会累加，因此排名提升。

#### 示例

如果一个文档在 BM25 第 1、FAISS 第 2：

```text
0.5/(1+60) + 0.5/(2+60)
```

如果另一个文档只在 BM25 第 1，则只有：

```text
0.5/(1+60)
```

因此被两路共同认可的文档通常排得更靠前。

#### 补充

- 当前实现按 `page_content` 精确去重，不是按文件名或语义去重；
- 内容相似但不完全相同的相邻 chunk 仍会作为不同候选；
- RRF 输出的是排名结果，项目没有把 RRF 分数附加回 Document。

---

### 问题 31：你发现的检索阈值问题是什么？

#### 建议回答

> 项目配置和接口说明把 `score_threshold` 描述为“越小越相关，2 相当于不过滤”，但当前 LangChain 的 `similarity_score_threshold` 返回 0～1 的 relevance score，越大越相关，实际过滤条件是 `similarity >= threshold`。所以默认值 2.0 会把 FAISS 正常结果全部过滤。
>
> 问题之所以隐蔽，是因为项目同时使用 BM25。即使 FAISS 返回空，BM25 仍能返回 `top_k`，API 仍是 200，页面看起来还能回答。我先直接查看运行环境中的 LangChain 源码确认阈值方向，再读取 FAISS 的真实相关度，把学习配置调整为 0.4并重启验证。

#### 后续实验依据

使用问题：

```text
FlashAttention为什么能减少HBM访问？
```

`top_k=5` 的控制实验：

| threshold | FAISS 通过数量 | 混合结果数量 | 实际状态 |
|---:|---:|---:|---|
| 0.0 | 5 | 5 | BM25 + FAISS |
| 0.4 | 3 | 5 | BM25 + FAISS |
| 0.6 | 0 | 5 | 退化为纯 BM25 |
| 0.8 | 0 | 5 | 退化为纯 BM25 |

> 这说明 `score_threshold` 只传给 FAISS，不是最终混合结果的统一质量阈值。把默认值改为 0.4只能恢复 FAISS 参与，不能解决 BM25 噪声和最终过滤问题。

---

### 问题 32：为什么接口返回的 `score` 都是 `3.0`？

#### 建议回答

> 混合检索器最终返回 `List[Document]`，不再返回 `(Document, score)`。API 中原本读取 `x[1]` 分数的代码已经被注释，当前构造 `DocumentWithVSId` 时只传入 ID、正文和 metadata，没有传 score；而 `DocumentWithVSId.score` 的默认值是 3.0。因此接口中的 3.0只是占位值，既不是 FAISS relevance score，也不是 BM25 或 RRF 分数。

#### 为什么重要

> 如果把 3.0误认为实际相关度，就会错误调参和监控。正确做法是明确返回每路原始分数、排名、融合分数或干脆不暴露含义不明的 score。

---

### 问题 33：为什么 BM25 会召回明显无关的 GitHub issue？

#### 建议回答

> 查询使用 `jieba.lcut_for_search()` 后，除了 `FlashAttention` 和 `HBM`，还产生了“什么、为什么、能、减少、访问、问号”等通用词。当前没有停用词过滤，BM25 又固定返回 `top_k` 条且没有最低分数阈值，因此正确关键词结果之后，会根据“为什么、使用、访问”等普通词补入无关 issue。RRF 使用排名而不是原始相关度，在两路等权时，这些 BM25 高排名噪声可能插入 FAISS 结果之间。

#### 实际分词

```python
[
    "FlashAttention", "什么", "为什么", "能",
    "减少", "HBM", "访问", "？"
]
```

#### 优化思路

```text
中文停用词和标点过滤
→ BM25最低分数或相对分数过滤
→ 两路权重和候选数可配置
→ RRF后增加Reranker
→ 最后截取真正需要的上下文
```

---

### 问题 34：当前 BM25 还有什么性能问题？

#### 建议回答

> `EnsembleRetrieverService.from_vectorstore()` 在每次查询时直接读取 `vectorstore.docstore._dict.values()` 中的全部 Document，然后对所有 chunk 重新执行 Jieba 分词并构建 BM25Retriever。当前只有 755 个 chunk，延迟还不明显；当知识库增长到十万或百万 chunk 时，构建成本和内存开销会成为瓶颈。更合理的方式是在入库或文档变更时构建、更新并缓存 BM25 索引，查询阶段只执行分词和检索。

#### 补充风险

- 直接使用 `_dict` 是依赖 LangChain 私有实现，升级版本时兼容风险较高；
- 每个请求在 FAISS 对象锁内构建和查询，可能扩大临界区；
- 当前缺少各阶段耗时指标，不容易判断瓶颈来自 Embedding、BM25 还是 LLM。

---

### 问题 35：`top_k` 在混合检索中是怎么用的？

#### 建议回答

> 当前实现把同一个 `top_k` 同时用于 FAISS 候选数、BM25 候选数和融合后的最终截断。假设 `top_k=5`，两路融合前最多产生十个未去重候选，RRF 排序后再截取五个。这样实现简单，但候选池和最终上下文大小被绑定，可能没有给 Reranker 或融合留下足够候选。生产中通常会区分 `vector_k`、`bm25_k`、`rerank_k` 和最终 `context_k`。

---

### 问题 36：Reranker 应该放在哪里？它和 RRF 有什么区别？

#### 建议回答

> RRF 根据多路排名融合，不直接深度判断 query 与文档内容；Reranker 通常使用 Cross-Encoder 或重排模型，同时读取 query 和候选文档，给出更精细的相关性判断。合理链路是先用 FAISS 和 BM25 进行高召回，再通过 RRF 合并候选，然后用 Reranker 精排，最后选少量文档进入 Prompt。

```text
FAISS/BM25召回较多候选
→ RRF合并去重
→ Reranker精排
→ 最终top_k
→ Prompt
```

#### 事实边界

> 当前 `kb_chat.py` 中的 Reranker 代码处于注释状态，我只分析了它应处的位置，不能说已经完成接入和效果验证。

---

## 6. Prompt、引用与回答生成

### 问题 37：检索文档如何送给大模型？

#### 建议回答

> `kb_chat()` 将检索到的 Document 正文通过双换行拼成 `context`，再读取 `prompt_settings.yaml` 中指定的 RAG Prompt，把 `context` 和用户 `question` 填入模板。历史消息和当前用户模板组成 ChatPromptTemplate，最后通过 `chain = chat_prompt | llm` 调用生成模型。

```python
context = "\n\n".join(doc["page_content"] for doc in docs)
prompt_template = get_prompt_template("rag", prompt_name)
chain = chat_prompt | llm
```

---

### 问题 38：`docs` 和 `source_documents` 有什么区别？

#### 建议回答

> `docs` 是检索返回的结构化正文和 metadata，主要用于构造 LLM 的 context；`source_documents` 是通过 `format_reference()` 根据文件名和 `public_host` 生成的用户可读出处，包括下载链接和文档片段。前者服务于模型生成，后者服务于页面展示和人工核验。

---

### 问题 39：没有检索到文档时，项目会怎样处理？

#### 建议回答

> 如果 `docs` 为空，`kb_chat()` 把 Prompt 名称切换为 `empty`。当前 empty 模板只是让模型直接回答问题，因此答案来自模型自身知识，不是知识库。服务端会向来源列表增加红色提示“未找到相关文档，该回答为大模型自身能力解答”。这种降级保证页面仍有回答，但需要明确标识来源，否则用户可能误以为答案有知识库证据。

---

### 问题 40：当前 RAG Prompt 有哪些优点和不足？

#### 建议回答

> 当前 Prompt 的优点是要求中文、禁止编造、规定无法从已知信息回答时的固定表述，并把指令、已知信息和问题分区。主要不足是没有要求关键结论逐条引用来源，没有规定多文档冲突的处理方式，没有把知识库文本明确限定为“数据而非指令”，因此缺少提示注入防御；另外 empty 模板本身也没有强调回答来自模型自身知识。

#### 工程化改进

> 不能只修改一句 Prompt。当前 context 只拼正文，模型不知道每段来自哪里。应先在 Context Builder 中为每个块加入稳定来源编号和文件名，再要求模型使用 `[来源1]` 引用，并在服务端验证引用编号合法。还可以给 metadata 增加版本、日期和权威等级，以支持冲突处理。

---

## 7. FastAPI、异步与流式输出

### 问题 41：为什么知识库检索使用 `run_in_threadpool()`？

#### 建议回答

> `search_docs()` 是同步函数，内部会进行 Embedding 请求、FAISS 查询、Jieba 分词和 BM25 构建。如果直接在 FastAPI 事件循环线程中运行，执行期间其他协程无法获得该线程。`run_in_threadpool()` 把同步工作交给工作线程，当前请求在 `await` 时暂停，事件循环可以继续接收和处理其他请求。

#### 不要说错

> 线程池不会让所有工作无限并行，也不能绕过 Python 和底层库的资源限制；大量 CPU 密集任务更适合受控线程池、进程池或后台任务系统。

---

### 问题 42：什么是异步？`async def` 是否代表函数会自动并行？

#### 建议回答

> 异步是一种协作式并发模型。事件循环运行一个协程，协程遇到真正可等待的 I/O 并执行 `await` 时，会保存当前状态并让出执行权；事件循环随后运行其他已就绪任务，等 I/O 完成后再恢复原协程。`async def` 只表示函数返回协程，并不保证内部代码自动并行。如果函数内部进行长时间本地计算而没有可让出执行权的 `await`，仍会阻塞事件循环。

#### 与 Java 的区别

> Java Web 服务常通过线程池让不同请求运行在不同线程；Python asyncio 可以在少量线程中管理大量 I/O 等待任务。两者都能并发处理请求，只是调度模型不同。生产系统也可以同时使用多进程、线程池和异步 I/O。

---

### 问题 43：知识库问答的 SSE 流式响应怎么实现？

#### 建议回答

> `kb_chat()` 创建 `AsyncIteratorCallbackHandler` 并把它作为回调传给 LLM。然后使用 `asyncio.create_task()` 在后台启动 `chain.ainvoke()`；主协程同时通过 `async for token in callback.aiter()` 消费模型生成事件，将每个 Token 包装成 `OpenAIChatOutput` 并由 `EventSourceResponse` 逐块发送给客户端。模型执行结束后，`wrap_done()` 标记 callback 完成，消费者退出，最后等待后台 task 收尾。

```text
模型生成Task
    └─ Callback写入Token队列
             ↓
主协程async for读取队列
             ↓
       SSE返回浏览器
```

---

### 问题 44：为什么要先 `create_task()`，不能直接 `await chain.ainvoke()`？

#### 建议回答

> 如果先 `await chain.ainvoke()`，当前协程会等完整模型调用结束后才继续读取 callback，无法边生成边返回。`create_task()` 先把模型执行注册为独立任务，随后当前协程立即进入 callback 的异步迭代。事件循环在模型网络 I/O、回调队列和 SSE 发送之间切换，从而实现实时输出。

---

### 问题 45：流式和非流式接口如何共用一套逻辑？

#### 建议回答

> 两种模式都使用同一个生成器和 Callback。流式模式每收到一个 Token 就立即构造 chunk 并 yield；非流式模式仍然遍历同一个 callback，只是先把 Token 累加到 `answer`，全部结束后返回一个 `chat.completion`。这样模型调用逻辑不需要维护两套，但非流式响应会增加一次服务端字符串聚合。

---

### 问题 46：客户端中途断开 SSE 会怎样？

#### 建议回答

> Starlette/FastAPI 会取消对应的响应任务，代码捕获 `asyncio.CancelledError` 并记录 `streaming progress has been interrupted by user`。这通常意味着浏览器关闭、刷新或 curl 主动终止，不一定是服务端故障。更完整的实现还应确认底层模型请求和后台 task 是否同步取消，避免客户端已离开但 GPU 仍继续生成。

---

### 问题 47：SSE 和 WebSocket 有什么区别？

#### 建议回答

> SSE 基于 HTTP 长连接，主要支持服务端向客户端单向推送文本事件，浏览器和代理支持简单，适合 LLM Token 流；WebSocket 建立全双工通道，客户端和服务端可以随时互发消息，更适合实时聊天室。我的网络靶场聊天室使用 WebSocket，而 Chatchat 的模型流式输出使用 SSE，二者都是实时反馈，但通信方向和协议复杂度不同。

---

## 8. Agent 控制循环

### 问题 48：当前项目的 Agent 调用流程是什么？

#### 建议回答

> WebUI 通过 OpenAI SDK 请求 `/chat/chat/completions`，路由层把字符串工具转换成 OpenAI 工具 Schema，并把 query、工具配置、会话 ID 等交给内部 `chat()`。`chat()` 创建模型和工具，调用 `create_models_chains()` 得到 PlatformToolsRunnable 和 AgentExecutor。Runnable 在后台执行 `agent_executor.ainvoke()`；真正的控制循环位于项目扩展的 `PlatformToolsAgentExecutor._acall()`：模型根据 input、history 和 intermediate_steps 生成 AgentAction 或 AgentFinish。AgentAction 会触发工具执行，工具结果作为 Observation 加入 intermediate_steps，再交给下一轮模型；AgentFinish 则结束循环并返回最终答案。

```text
Input
→ LLM决策
  ├─ AgentAction
  │    → Tool
  │    → Observation
  │    → intermediate_steps
  │    → 下一轮LLM
  └─ AgentFinish
       → 最终回答
```

---

### 问题 49：这些 Agent 状态分别代表什么？

#### 建议回答

| 状态对象 | 含义 |
|---|---|
| `PlatformToolsAction` | 模型已经决定调用哪个工具以及生成什么参数 |
| `PlatformToolsActionToolStart` | 工具即将或已经开始执行 |
| `PlatformToolsActionToolEnd` | 工具执行结束，产生 Observation/工具输出 |
| `PlatformToolsFinish` | Agent 不再调用工具，给出最终结果 |
| `PlatformToolsLLMStatus` | 模型开始、输出 Token、结束或链状态等事件 |

> 必须区分“控制循环”和“状态输出”：`_acall()` 决定模型、工具和下一轮执行；`chat.py` 中的 `async for item` 只是消费这些事件并转成前端响应，不负责决定下一步调用哪个工具。

---

### 问题 50：`self.agent_executor` 是什么？为什么当前类中找不到 `ainvoke()`？

#### 建议回答

> `self.agent_executor` 是创建 Agent 时返回的 `PlatformToolsAgentExecutor`，它继承 LangChain 的 `AgentExecutor`，而 AgentExecutor 又属于 LangChain Runnable/Chain 调用体系。`ainvoke()` 是继承得到的统一异步调用入口，不一定直接定义在项目子类文件中。调用 `ainvoke()` 后，LangChain 的通用入口最终分派到子类覆盖的 `_acall()`，所以项目通过重写 `_acall()` 定制了真正的异步 Agent 循环。

#### 源码关系

```text
PlatformToolsAgentExecutor
        ↓ 继承
LangChain AgentExecutor
        ↓ Runnable/Chain调用协议
ainvoke()
        ↓ 最终调度
PlatformToolsAgentExecutor._acall()
```

---

### 问题 51：`intermediate_steps` 保存什么？为什么必须回传给模型？

#### 建议回答

> 它保存已经执行过的 `(AgentAction, Observation)`。AgentAction 记录模型选择的工具和参数，Observation 是工具返回值。下一轮模型调用会把这些步骤转换成 scratchpad 或消息，使模型知道自己已经做过什么、工具返回了什么，然后决定继续调用其他工具还是输出 AgentFinish。如果不回传，模型会丢失工具结果，可能重复调用或者无法基于结果生成最终答案。

---

### 问题 52：Agent 循环是 LangChain 实现的还是项目实现的？

#### 建议回答

> 两者都有。LangChain 提供 AgentExecutor、Runnable、AgentAction、AgentFinish、BaseTool 和 Callback 等基础抽象；Langchain-Chatchat 继承 AgentExecutor，重写 `_call()` 和 `_acall()`，加入 MCP 工具、平台工具事件、已有 intermediate_steps 和自定义输出解析，并在外层将回调状态转换成 OpenAIChatOutput。因此不能说全部是项目从零实现，也不能说项目只调用了 LangChain 一个黑盒 API。

---

### 问题 53：你是否已经开发自定义工具并接入 MCP？

#### 建议回答

> 当前没有把它作为已完成项。我已经追踪了工具 Schema、模型工具选择、参数生成、工具执行、Observation 回传和多轮决策源码，也理解 MCP 工具会在创建 AgentExecutor 时与本地工具组合，但还没有完成一个带测试的自定义工具和独立 MCP Server 实战，所以简历中只写“深入分析 Agent 执行流程”，没有写“完成自定义工具和 MCP 开发”。

这个回答比夸大经历更可信。如果面试官继续问计划，可以回答：

> 下一步会实现一个输入结构明确的文本统计工具，加入 Pydantic 参数校验、超时、异常返回和单元测试，再分别通过 `/tools/call` 和 Agent 自动选择验证；之后再接最小 MCP Server。

---

## 9. 真实问题排查与工程能力

### 问题 54：请介绍一次最有代表性的故障排查

#### 建议回答：检索阈值问题

> 现象是知识库搜索在阈值设为 1.5 时仍然返回三条结果，而且每条 score 都是 3.0。第一步我没有直接修改参数，而是从 `/knowledge_base/search_docs` 追踪到 KBService、FaissKBService 和 EnsembleRetriever。第二步发现 threshold 只传给 FAISS，BM25 不使用它。第三步使用 `inspect.getsource()` 查看当前安装的 LangChain 源码，确认 relevance score 范围是 0～1、越大越相关，过滤条件是大于等于阈值，所以 1.5 和默认 2.0会清空 FAISS。接口仍有结果是因为 BM25 掩盖了问题。继续追踪后发现 score=3.0来自响应模型默认值，并非真实分数。
>
> 处理上，我先把学习环境阈值调整为 0.4并重启 API，通过 OpenAPI 默认值和 FAISS 原始分数验证配置生效；随后又测试 0、0.4、0.6、0.8，证明 0.6以上 FAISS 为零但混合结果仍有五条。最终结论是修改 0.4只能恢复向量分支，完整优化还需要统一阈值语义、处理 BM25 噪声并增加最终重排。

#### 这个回答体现什么

```text
从现象出发
→ 跟踪调用链
→ 核对依赖真实源码
→ 设计对照实验
→ 区分临时配置修正和根本设计优化
```

---

### 问题 55：WebUI 的 `UnboundLocalError` 是怎么解决的？

#### 建议回答

> 页面在未启用 Agent 时抛出 `local variable 'use_mcp' referenced before assignment`。我检查 `dialogue.py` 后发现 `use_mcp` 只在 `if use_agent:` 分支中赋值，但构造 `extra_body` 时无条件读取。修复是在进入分支前设置安全默认值 `use_mcp=False`，启用 Agent 后再由复选框覆盖。之后使用 AST 解析和 `git diff --check` 做静态检查，重启 WebUI，普通对话和知识库页面恢复正常。

#### 为什么不是简单捕获异常

> 根因是控制流中变量没有覆盖所有路径，捕获异常只会隐藏错误。为变量提供符合业务含义的默认值才能保证未启用 Agent 的正常路径。

---

### 问题 56：你做过哪些测试和验证？

#### 建议回答

> 当前主要完成了分层手工验证。模型层调用 Ollama generate 和 embed；应用层检查 Swagger、OpenAPI、知识库列表和文档检索；模型网关完成 `/v1/chat/completions` 非流式和 SSE 流式请求，并测试客户端主动中断；WebUI 验证普通对话、RAG 问答和来源下载；数据层检查 FAISS 文件以及 SQLite 的知识库、文件和文档块数量；算法层完成三组分块实验和多阈值混合检索实验。

#### 自动化测试边界

> 我安装了 pytest，但项目 `pyproject.toml` 中存在当前环境未安装插件提供的 `--snapshot-warn-unused` 参数，测试启动阶段出现参数不识别；因此不能说完整自动化测试已经通过。面试中应说明目前是手工集成验证，后续需要补齐测试依赖并建立可重复的接口和 RAG 评测。

---

### 问题 57：如果继续优化这个项目，你会优先做什么？

#### 建议回答

> 我会先解决可观测性和检索质量，再做更重的模型优化。第一，统一 score 的定义，修正接口文档和默认阈值，并返回每路检索的真实排名或分数；第二，为 BM25 增加停用词、质量阈值和缓存索引；第三，扩大两路候选后加入 Reranker，再缩小最终上下文；第四，重构 Context Builder 和 Prompt，增加来源编号、冲突处理和提示注入防御；第五，建立固定问题集，评估 Recall@K、MRR、答案正确性和引用准确性；最后再考虑异步入库、权限隔离、监控和横向扩展。

---

### 问题 58：如果知识库增长到一百万个 chunk，当前方案会遇到什么问题？

#### 建议回答

> 首先，当前每次查询从 Docstore 读取全部 Document 并重建 BM25，无法扩展到百万级；其次，单机内存中的 FAISS、Docstore 和全局锁会限制并发和容量；SQLite 更适合作为当前单机学习环境的业务元数据存储，不适合高并发多租户；文档上传和向量化在请求链中执行也容易超时。生产化时我会持久化并增量维护全文索引，选择支持分片和过滤的向量数据库，使用关系数据库管理元数据，通过消息队列异步入库，并建立任务状态、失败重试和幂等机制。

---

### 问题 59：如何利用你以前的 RabbitMQ 经验改造知识库入库？

#### 建议回答

```text
上传接口
→ 保存原文件并创建任务记录
→ 发送文档处理消息
→ Worker执行解析、分块、Embedding和索引更新
→ 分阶段更新任务进度
→ WebUI通过SSE或WebSocket观察进度
→ 失败重试或进入死信队列
```

> 还需要使用知识库名、文件哈希和版本设计幂等键，避免消息重试造成重复向量；FAISS 和数据库写入不是同一事务，因此需要补偿逻辑或先写临时版本、完成后原子切换。

---

### 问题 60：为什么从 Java 后端、视觉模型实习转向学习 LLM 应用？

#### 建议回答

> 我的核心方向不是放弃后端，而是把后端工程能力与模型能力结合起来。Java 工作让我积累了 API、消息队列、WebSocket、数据库和云资源编排经验；BEVFormer 实习让我经历了数据、训练、ONNX 和端侧部署；Langchain-Chatchat 项目进一步补齐了 LLM、Embedding、RAG、Agent 和流式服务。我的优势是既能理解模型链路，也重视系统的可部署、可调试和可维护性。

---

## 10. 面试官可能进行的连续追问

### 10.1 围绕检索阈值连续追问

```text
问：为什么阈值2.0还有结果？
答：FAISS为空，但BM25仍返回结果。

问：你怎么证明FAISS为空？
答：查看LangChain实际过滤源码，并分别打印纯FAISS结果。

问：为什么score都是3.0？
答：响应模型默认值，没有传真实分数。

问：改成0.4就彻底解决了吗？
答：没有，只恢复FAISS参与，BM25仍绕过阈值。

问：怎样根治？
答：统一分数语义、BM25过滤、Reranker、最终质量控制和评测。
```

### 10.2 围绕 Chunk 连续追问

```text
问：为什么750/150最好？
答：在当前文档和三个问题中，Top1证据完整性最好。

问：是不是所有文档都用750/150？
答：不是，需要按文档类型和评测结果选择。

问：150是否精确重叠？
答：不是，算法按完整子片段滑动。

问：应该用字符还是Token？
答：当前按字符，生产中还应结合Embedding和LLM tokenizer限制。
```

### 10.3 围绕 Agent 连续追问

```text
问：谁决定调用工具？
答：模型输出经Parser解析为AgentAction。

问：谁真正执行工具？
答：PlatformToolsAgentExecutor的下一步执行逻辑。

问：工具结果如何回到模型？
答：作为Observation加入intermediate_steps并构造下一轮scratchpad。

问：什么时候结束？
答：模型产生AgentFinish，或达到迭代/时间限制及提前终止条件。

问：chat.py的async for是不是控制循环？
答：不是，它是事件消费者，控制循环在_acall中。
```

---

## 11. 高频事实速查

| 项目 | 当前实际值 |
|---|---|
| Langchain-Chatchat | 0.3.1.3 |
| Python | 3.10.20 |
| LangChain | 0.1.17 |
| Ollama | 0.32.15 |
| LLM | qwen2:7b |
| Embedding | bge-m3 |
| Embedding 维度 | 1024 |
| 知识库 | samples |
| 文件数量 | 12 |
| Chunk 数量 | 755 |
| 向量库 | FAISS |
| 业务数据库 | SQLite |
| Chunk 参数 | 750/150 |
| 默认 Top K | 3 |
| 当前学习阈值 | 0.4 |
| API | 7861 |
| WebUI | 8501 |
| Ollama | 11434 |
| 服务器访问地址 | 10.10.12.248 |

---

## 12. 面试时最容易说错的内容

### 12.1 分数方向

错误：

```text
当前LangChain相关度越小越相关。
```

正确：

```text
当前similarity_score_threshold使用0～1 relevance score，越大越相关，
过滤条件是similarity >= threshold。
```

### 12.2 `score=3.0`

错误：

```text
3.0是RRF融合分数。
```

正确：

```text
3.0是DocumentWithVSId的默认占位值。
```

### 12.3 FAISS 存储

错误：

```text
正文保存在index.faiss中。
```

正确：

```text
index.faiss保存数值索引；正文和metadata位于index.pkl中的Docstore。
```

### 12.4 OCR

错误：

```text
OCR可以理解图表趋势。
```

正确：

```text
当前OCR主要提取图片文字，代码还丢弃了文字坐标和置信度。
```

### 12.5 异步

错误：

```text
只要写async def，本地长计算就不会阻塞。
```

正确：

```text
只有在可等待操作上await并让出执行权，事件循环才能运行其他任务。
```

### 12.6 已完成功能

错误：

```text
我已经完成Reranker、自定义工具和MCP开发。
```

正确：

```text
目前完成对应源码分析，实装和系统测试仍是后续计划。
```

---

## 13. 面试前优先背熟的十个答案

1. 两分钟项目介绍；
2. 个人贡献与项目原有能力的边界；
3. 三服务架构和端口；
4. 文档上传到 FAISS/SQLite 的完整入库链；
5. `300/50`、`750/150`、`1200/200` 实验结论；
6. 用户问题到 Prompt 和 Qwen2 的完整查询链；
7. FAISS、BM25 和 RRF 的区别；
8. 阈值语义、BM25 掩盖 FAISS 失效和 `score=3.0`；
9. `create_task + Callback + SSE` 的流式原理；
10. AgentAction、Tool、Observation、intermediate_steps、AgentFinish 的循环。

如果回答时间有限，优先用“结论 → 一条代码证据 → 一个实验结果”的结构。例如：

```text
结论：阈值只过滤FAISS。
代码证据：score_threshold只传给faiss_retriever，BM25只设置k。
实验结果：threshold=0.6时FAISS为0，混合结果仍有5条。
```

这种表达比从头背诵全部源码更适合真实面试。
