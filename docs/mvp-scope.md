# MVP 范围（M0 - M4）

## M0：项目规范与工程骨架

### 范围

- 项目级文档（README、CLAUDE、product-requirements、architecture、mvp-scope、development-roadmap、evaluation-design、ADR）
- Python 工程骨架（pyproject、ruff、mypy、pytest 配置）
- 长期稳定的 Protocol：Tool、TaskRepository、Tracer
- 领域模型：Task、Trace、Report
- FastAPI App + `GET /api/v1/health`
- 启动脚本（Windows + WSL）
- 健康检查测试

### 不做

- LangGraph 编排
- AgentState
- 任何 Graph Node
- 任务 API（POST /tasks 等）
- InMemoryTaskRepository 实现
- 真实或 Mock LLM 客户端
- Prompt 模板
- 示例 Bug 项目
- 代码搜索或任何工具实现
- BM25、FAISS、Tree-sitter
- 任何准确率或虚构执行结果

### 验收标准

1. `uv sync` 成功
2. `uv run ruff check src/ tests/` 通过
3. `uv run mypy --strict src/` 通过
4. `uv run pytest tests/ -v` 通过
5. `uv run uvicorn springfix_agent.main:app --port 8000` 可启动
6. `GET http://localhost:8000/api/v1/health` 返回 `{"status":"ok","version":"0.1.0"}`
7. `GET http://localhost:8000/docs` 返回 OpenAPI 文档
8. 未创建任何 M1/M2 提前实现文件

---

## M1：确定性垂直切片

### 范围

- `POST /api/v1/tasks` 提交诊断任务
- `GET /api/v1/tasks/{task_id}` 查任务状态
- `GET /api/v1/tasks/{task_id}/traces` 查工具调用和节点耗时
- `GET /api/v1/tasks/{task_id}/report` 查基础报告
- LangGraph 4 节点线性图：
  - `validate_input`
  - `explore_repository`
  - `retrieve_code`
  - `build_basic_report`
- 4 个工具最简实现：
  - `list_project_tree`：`os.walk` + 过滤
  - `search_code`：简单确定性词法评分（不引入 BM25）
  - `read_file`：行切片 + 沙箱校验 + 截断
  - `find_java_symbol`：正则匹配
- `InMemoryTaskRepository` 实现 `TaskRepository` Protocol
- `InMemoryTracer` 实现 `Tracer` Protocol
- `TaskService.submit_task` + `TaskService.run_task_sync`
- `AgentState`（M1 版，仅确定性字段）
- 1 个示例 Bug 项目：`transaction-self-invocation`
- 路径校验模块 `tools/_path_safety.py`
- 工具单元测试 + 1 个端到端集成测试

### 不做

- 任何真实 LLM 调用
- IssueParser / TaskPlanner / RootCauseAnalyzer（M2）
- BM25、Java 标识符分词、块级切分（M3）
- SQLite 持久化（M4）
- 评测运行器与指标输出（M4）
- Vue 前端、Spring Boot 后端、MySQL/Redis/MinIO
- Docker 沙箱、Maven 测试执行、自动代码修改
- 反思、回退、多 Agent、HITL
- SSE / WebSocket

### 验收标准

1. POST /tasks 接收合法请求返回 task_id
2. POST /tasks 对非法路径、空描述、超出 allow_root 返回 400
3. LangGraph 4 节点完整流转
4. 每次工具调用有 tool_name / params / duration_ms / status / result_summary
5. 端到端测试提交 sample-bug 后 60s 内完成
6. 所有节点 State 字段被填充
7. find_java_symbol 从 error_log/issue_description 提取符号，不硬编码
8. search_code 无命中时返回空，不伪造候选
9. ruff + mypy strict + pytest 全部通过
10. README 含启动命令、API curl 示例、执行结果

---

## M2：LLM 推理节点（已完成）

### 范围

- 7 节点 LangGraph：validate_input → issue_parser → task_planner → explore_repository → retrieve_code → root_cause_analyzer → build_diagnostic_report
- LLM 客户端抽象：Protocol + MockLLMClient + OpenAICompatibleLLMClient
- Pydantic 结构化输出：IssueAnalysis / InvestigationPlan / RootCauseAnalysis
- 超时 / 重试 / 降级策略
- Prompt 模板（.md 文件）
- Prompt Injection 防护
- LLM Trace
- Live 诊断脚本 `scripts/run_live_diagnosis.py`
- Mock 模式默认，无 API Key 也能运行

### 不做

- BM25 / Embedding / FAISS / Tree-sitter（M3）
- SQLite 持久化（M4）
- Vue 前端 / Spring Boot 后端
- Docker 沙箱 / Maven 测试执行 / 自动代码修改
- 多 Agent / 反思 / 循环

### 验收标准

1. 7 节点按顺序执行
2. IssueParser / TaskPlanner / RootCauseAnalyzer LLM 失败时正确降级
3. RootCauseAnalyzer 二次业务校验拒绝无效 evidence
4. 报告区分 complete / partial / insufficient_evidence
5. Prompt Injection 不改变系统行为
6. LLM Trace 记录在 traces 响应中
7. API 不暴露 Prompt 和模型完整响应
8. Mock 模式 + 健康检查在无 API Key 时正常
9. ruff + mypy strict + pytest 全部通过
10. Live 诊断脚本在配置齐全时能运行（未配置时不伪造结果）

### 当前运行边界

- 三个真实模型 Live Case 仅为回归结果，不代表准确率
- Prompt Injection Case 不代表绝对安全
- 检索仍为 M1 简单词法评分；BM25 在 M3 实现
- 当前使用 InMemory 存储和进程内后台线程
- Agent 不执行 Maven、不执行用户代码，也不修改代码

---

## M3：代码检索增强

### 范围

- BM25 实现（替换 M1 的简单词法评分）
- Java 标识符分词
- `find_java_symbol` 优化分词和切分
- 方法级或代码块级切分
- 检索指标对比（M1 简单词法 vs BM25，Recall@K）
- AgentState 扩展 M3 字段

### 不做

- Embedding、FAISS（后续）
- Tree-sitter AST（后续）

---

## M4：持久化与评测

### 范围

- `SqliteTaskRepository` 实现 `TaskRepository` Protocol
- SQLite Schema 与迁移
- 至少 3 个可复现 Spring Boot Bug 样本
- 评测 Runner `scripts/run_eval.py`
- 评测指标报告输出
- README 补充实际评测结果

### 评测指标

- `issue_category_accuracy`
- `key_file_recall@5`
- `root_cause_hit@1`
- `root_cause_hit@3`
- `average_duration_ms`
- `tool_call_count`
- `llm_call_count`

### 不做

- 伪造准确率或命中率数据
- LangSmith / Langfuse 上传
