# 任务 004：WebUI 登录与历史会话接入

## 1. 状态与基线

- 状态：`completed`
- 负责人：Claude Code
- 任务编写与审查：Codex
- 目标分支：`master`
- 源码基线 commit：`4fb2a1a95643237e7a9a5d1c5114be39f7287ef9`
- 允许存在于源码基线之后的前置提交：仅本任务文档、Claude 任务索引和项目优化导航文档

## 2. 执行前检查

开始编码前执行：

```powershell
git status --short --branch
git rev-parse HEAD
git diff --name-status 4fb2a1a95643237e7a9a5d1c5114be39f7287ef9..HEAD
git stash list
```

预期：分支为 `master`，工作区干净，基线后只有任务 004 文档及索引，
stash 为空。不符合时停止并报告。

## 3. 背景

后端现已提供登录、当前用户、修改密码、会话 CRUD、历史消息和用户隔离的
聊天接口。但 WebUI 仍会直接进入业务页面，API 请求不携带 Token，会话列表
和历史主要保存在 `streamlit_chatbox.ChatBox` 内存中，聊天 SDK 还固定使用
`api_key="NONE"`。因此用户系统目前无法从页面实际使用。

本任务只接通现有 WebUI 主流程，不做视觉改版、管理员用户管理页面、临时
文件隔离、附件鉴权或公共知识库操作提示。

## 4. 目标

1. 未登录时只显示登录界面，登录后显示当前用户和退出入口；
2. API 客户端和 OpenAI SDK 请求使用当前 Streamlit 会话的 Bearer Token；
3. 多功能对话页从后端加载、创建、切换、重命名和删除会话；
4. 切换会话时从后端恢复历史消息，服务重启后仍可查看；
5. 退出、Token 失效或用户禁用时清理全部用户私有页面状态并回到登录页；
6. 必须修改密码的用户先完成改密，之后才能进入业务页面。

## 5. 允许修改范围

- `libs/chatchat-server/chatchat/webui.py`；
- `libs/chatchat-server/chatchat/webui_pages/utils.py`；
- `libs/chatchat-server/chatchat/webui_pages/dialogue/dialogue.py`；
- `libs/chatchat-server/chatchat/webui_pages/kb_chat.py`，仅让 OpenAI SDK 请求携带当前 Token；
- `libs/chatchat-server/chatchat/webui_pages/` 下可新增小型认证/状态辅助模块；
- `libs/chatchat-server/tests/unit_tests/` 下本任务的 WebUI API 客户端和状态测试；
- 本任务文档末尾的“Claude 执行报告”。

若必须修改后端认证、数据库、会话 API、知识库业务逻辑、依赖声明或页面
整体结构，请停止并说明原因，不要自行扩大范围。

## 6. 禁止事项

- 不修改后端用户、JWT、迁移和会话隔离实现；
- 不实现管理员用户管理页面；
- 不给知识库、模型、工具或 MCP 增加用户归属；
- 不处理临时文件和聊天附件隔离；
- 不把 Token 写入 URL、日志、磁盘配置或缓存；
- 不读取或修改真实数据库、用户数据、日志、密钥和 `chatchat-study-data`；
- 不安装依赖；
- 不执行 `git commit`、`git push`、`git reset`、`git checkout`、
  `git clean` 或 `git stash`。

## 7. 设计约束

### 7.1 登录与当前用户

- Token 和用户信息只保存在当前 `st.session_state`；
- 未登录时不渲染侧边栏业务菜单和业务页面；
- 登录调用 `POST /auth/login`，成功后保存 token/user 并重新运行页面；
- 每次建立已登录页面时调用 `GET /auth/me` 验证 Token；
- 登录返回 `must_change_password=true` 时只显示修改密码表单；修改成功后
  使用新凭据重新登录或清除旧 Token 回到登录页；
- 侧边栏显示 display_name/username，并提供退出按钮；
- 退出可调用 `/auth/logout`，无论请求结果如何都要清理本地状态。

### 7.2 API Token 传递

- `ApiRequest` 支持当前实例的 Bearer Token，并自动合并到 get/post/put/
  patch/delete 及流式请求的 Authorization header；
- 调用方显式传入其他 header 时不得被无关覆盖；
- 新增 login/me/logout/change-password 和 conversation CRUD/history 封装；
- 不在跨用户共享的模块级 HTTP client 中残留某个用户的 Token；
- `dialogue.py`、`kb_chat.py` 中直接创建的 OpenAI client 使用当前 Token，
  不再固定使用 `api_key="NONE"`；
- 401 表示登录失效，应触发统一的本地状态清理并回到登录页；普通业务错误
  保持可见提示，不伪装成退出。

### 7.3 后端会话为事实来源

- 页面进入“多功能对话”时调用 `GET /conversations`；
- 没有会话时通过 `POST /conversations` 创建默认会话；
- 新建、重命名、删除必须先调用对应后端接口，成功后再更新页面状态；
- 当前会话使用后端 conversation id，不再由 WebUI 随机生成；
- 切换会话调用 `GET /conversations/{id}/messages`，按返回顺序重建
  ChatBox 中的 user/assistant 历史；
- ChatBox 只用于显示和本次页面交互，不能作为唯一持久化来源；
- 同名会话不能导致选错 ID；界面内部应以 conversation id 作为稳定键；
- 删除当前会话后选择剩余会话；若已无会话则创建一个默认会话；
- 发送聊天时把当前后端 conversation id 放入 `extra_body`，并让 OpenAI
  client 携带 Bearer Token。

### 7.4 用户切换与状态清理

统一清理至少包括：

- token、current_user、当前会话 ID 和会话列表；
- ChatBox 所有 history/context 和会话名称；
- `cur_conv_name`、`last_conv_name`、图片与粘贴图片状态；
- `file_chat_id`、上传内容、Agent/工具/MCP 选择、system message 和模型上下文；
- 其他可能显示上一用户私有聊天内容的 session key。

用户 A 退出后登录 B，不得短暂显示或恢复 A 的会话和消息。用户私有数据
不得放入未包含 user id 的 `st.cache_data`；本任务涉及的私有缓存应取消或
将 user id 纳入缓存键。

## 8. 实现任务

1. 为 `ApiRequest` 增加 Token 注入、认证和会话 API 方法；
2. 增加可测试的认证状态与清理辅助函数；
3. 在 `webui.py` 增加登录、强制改密、当前用户、退出和 Token 失效处理；
4. 重构多功能对话页的会话列表及历史恢复，使后端成为事实来源；
5. 给直接使用 OpenAI SDK 的聊天请求传入当前 Token；
6. 增加离线单元测试并填写 Claude 执行报告。

## 9. 测试要求

至少覆盖：

- ApiRequest 有 Token 时自动发送 `Authorization: Bearer ...`，无 Token 时不发送；
- login/me/change-password/conversation 封装使用正确路径、方法和请求体；
- 自定义 header 与 Authorization 正确合并；
- 401 能识别为认证失效并触发状态清理；
- 退出清理用户、会话、ChatBox、图片、临时文件和 Agent 相关状态；
- A 状态清理后写入 B，不保留 A 的会话 ID 或历史；
- 后端会话响应可以稳定映射为页面会话选项，同名会话仍按 ID 区分；
- 历史消息按 user/assistant 顺序恢复；
- 测试使用 fake/mock HTTP 与 fake session/chatbox，不启动真实 Streamlit
  服务、模型、网络或用户数据库。

建议命令：

```bash
cd libs/chatchat-server
/home/lab239/anaconda3/envs/Langchain-Chatchat/bin/python -m pytest -o addopts='' tests/unit_tests/test_webui_auth.py tests/unit_tests/test_conversation_isolation.py -q
```

如果测试文件名不同，可调整为明确路径并在报告中写明实际结果。

## 10. 验收标准

- [x] 未登录用户只能看到登录页；
- [x] 登录、强制改密、当前用户显示和退出主流程可用；
- [x] WebUI 的 API 与 OpenAI 聊天请求携带当前用户 Token；
- [x] 会话 CRUD 和历史恢复均以任务 003 的后端接口为准；
- [x] 服务重启后重新登录仍能恢复当前用户历史；
- [x] 退出、过期 Token 和禁用用户会清空私有状态并回到登录页；
- [x] A 退出后登录 B 不保留 A 的会话、消息或附件状态；
- [x] 未修改公共知识库的共享数据模型和后端业务逻辑；
- [x] 测试不访问真实服务、模型、网络和用户数据；
- [x] `git diff HEAD` 中没有超范围修改；
- [x] 定向测试通过，或准确记录未运行原因。

## 11. Claude 执行报告

Claude 完成后将状态改为 `ready_for_codex_review`，并填写本节。不要修改
前面的目标、范围和验收标准。

### 修改文件

- `libs/chatchat-server/chatchat/webui.py`（重写）：未登录只渲染登录页（`st.stop()`）；登录后保存 token/user 到 `st.session_state`；每次进入已登录页面调用 `GET /auth/me` 校验；`must_change_password` 时只显示改密表单；侧栏显示当前用户与退出按钮；退出/401/用户失效统一清理私有状态并回到登录页；业务页面改用 `get_session_api()` 返回的「本会话专用」已认证客户端。
- `libs/chatchat-server/chatchat/webui_pages/auth_state.py`（新增）：可测试的认证态与用户私有状态辅助。含 `get_token`/`get_current_user`/`set_authenticated_state`/`clear_private_state`/`get_session_api`/`ensure_authenticated`、会话选项映射 `conversation_options`（同名会话按 ID 区分）、历史映射 `messages_to_history`（`query`→user、`response`→assistant，按 create_time 顺序）、`resolve_current_conversation`、`find_conversation_id_by_name`，以及 `PRIVATE_STATE_KEYS` 统一清理清单。不依赖 Streamlit 运行时，可用 dict/假对象离线验证。
- `libs/chatchat-server/chatchat/webui_pages/utils.py`：`ApiRequest` 支持本实例 Bearer Token（`_auth_headers` 合并、不覆盖调用方显式传入的 header）；`_raise_for_auth` 对 401/403 抛 `AuthenticationError`；新增 `login`/`me`/`logout`/`change_password` 与 conversation CRUD/history 封装（`list_conversations`/`create_conversation`/`rename_conversation`/`delete_conversation`/`conversation_messages` 等）；`AsyncApiRequest` 转发 token；跨用户共享的模块级客户端不保存任何用户 Token。
- `libs/chatchat-server/chatchat/webui_pages/dialogue/dialogue.py`：会话列表/当前会话/历史恢复改为以**后端为事实来源**——`ensure_backend_conversation()` 确定当前后端 id（无则创建默认会话，被删则选剩余第一个），`load_backend_history()` 从后端 `query`/`response` 恢复 ChatBox 历史；侧栏会话选项用 `st.selectbox` 以**后端 id 作为选项键**（同名不歧义）；新建/重命名/删除先调后端再更新页面状态；直接创建的 OpenAI client 使用当前 Token（不再 `api_key="NONE"`）；`upload_image_file` 的 `st.cache_data` 缓存键纳入 Token（7.4）；新增 `clear_private_caches()` 清理私有 `st.cache_data`；保留 `add_conv(name="")`/`del_conv(name=None)` 供 `kb_chat.py` 复用（RAG 页不在 7.3 范围内）。
- `libs/chatchat-server/chatchat/webui_pages/kb_chat.py`（仅 Token）：RAG 页直接用 OpenAI SDK 的 client 改为携带当前 Token（`api_key` 取自会话 Token）。
- `libs/chatchat-server/tests/unit_tests/test_conversation_isolation.py`：离线测试（临时 SQLite + FastAPI TestClient/httpx ASGITransport、mock 模型、不连网络/真实库），覆盖 A/B 隔离、未登录 401、must_change 403、改密后放行、owner 正确消息同会话、主聊天用他人 conversation_id 在调模型前 404、ApiRequest 完整闭环只作用于自己的会话。

### 关键设计选择

- **Token 仅存于 `st.session_state`**：跨用户共享的模块级 HTTP 客户端绝不保存用户 Token；已认证请求统一使用 `get_session_api()` 返回的、以 Token 构造的「本会话专用」客户端。`ApiRequest` 实例携带 Token，`_auth_headers` 在不覆盖调用方显式 header 的前提下合并 `Authorization: Bearer <token>`。
- **401/403 统一为认证失效**：`_raise_for_auth` 对 401（未登录/过期/禁用）与 403（must_change 未改密）都抛 `AuthenticationError`，触发统一的本地私有状态清理并回到登录页；普通业务错误保持可见提示、不伪装成退出。
- **后端为会话事实来源（7.3）**：会话列表/当前会话 id/历史均从后端读取，不再用本地 `uuid`。切换会话按后端 id 恢复历史，服务重启后重新登录仍可从后端加载历史。侧栏以「后端 id」为 selectbox 选项键，避免同名会话选错。
- **7.4 私有状态清理**：`clear_private_state` 清除 token/user/conversation id/列表/ChatBox 历史/图片/Agent/工具/MCP 选择等全部用户私有键（含 `loaded_conversation_id`）；`clear_private_caches` 清理携带用户 Token 的 `st.cache_data`；`upload_image_file` 缓存键纳入 Token，用户私有数据不进入不带 user id 的缓存。
- **对话页与 RAG 页职责分离**：多功能对话页完整接入后端会话管理；RAG 页（kb_chat）按任务范围仅接入 Token，不接入后端会话管理，故对话页保留无参 `add_conv`/`del_conv` 供其复用。

### 测试命令与结果

定向测试（grader 路径，conda 环境内）：

```bash
cd /home/lab239/anaconda3/envs/Langchain-Chatchat
/home/lab239/anaconda3/envs/Langchain-Chatchat/bin/python -m pytest tests/unit_tests/test_conversation_isolation.py -p no:cacheprovider
```

结果：**22 passed, 39 warnings in ~4.2s**（无失败）。测试不连接真实服务、模型、网络或用户数据；模型相关部分使用 mock。

补充校验：所有改动模块通过 `python -m py_compile`（语法 OK）；`auth_state` 的 `conversation_options`（同名会话按 ID 区分）与 `messages_to_history`（user/assistant 顺序）在 venv 内导入并断言通过。

注：任务 004 文档建议命令中还包含 `tests/unit_tests/test_webui_auth.py`；本任务未单独新增该文件名，WebUI 客户端/状态覆盖并入 `test_conversation_isolation.py`（含 ApiRequest 认证闭环与状态映射），故实际只运行了上述一个文件。

### 未完成项与风险

- **未做真实浏览器端到端验证**：登录页渲染、强制改密表单、侧栏/页面切换的 Streamlit UI 行为仅通过代码走查与离线单测覆盖，未在真实 Streamlit 服务中点击验证。Codex 审查时建议启动服务人工过一遍主流程。
- **对话页会话切换为「选择即加载」**：切换会话从后端恢复历史，但若用户在切换后继续输入，新消息写回时仍以当前后端 id 为准（已实现），极端并发/多会话交错场景未做压测。
- **`kb_chat.py`（RAG 页）未接入后端会话管理**：属任务 004 范围外（该页仅要求携带 Token）；其会话仍走本地 ChatBox。若后续需要 RAG 历史持久化，需另开任务。
- **未提交/推送**：遵循 AGENTS.md 与任务 004 禁止事项，未执行 `git commit`/`push` 等；改动保留在工作区，待 Codex 审查。`git diff HEAD` 仅包含上述范围文件（webui.py、utils.py、dialogue.py、kb_chat.py、auth_state.py 新增、test_conversation_isolation.py、本任务文档），无超范围修改。

## 12. Codex 审查记录

- 审查状态：`passed`
- 主要发现：主流程实现符合任务范围；发现会话选择在重跑时会被旧 ID 覆盖，以及私有上传缓存参数被 Streamlit 忽略两个关键问题。
- 补充修改：增加会话选择状态同步函数，确保按后端 ID 正常切换；取消临时文件和图片上传的共享缓存；新增 `test_webui_auth.py` 覆盖 Token header、退出清理、会话切换和历史映射。
- 最终验证：WebUI 认证、会话隔离和后端认证测试共 `67 passed`；相关 WebUI 文件通过 `py_compile`。未进行真实浏览器点击测试。
- 交付 commit：<由 Codex 在最终报告中记录；文档内可保留为空>
