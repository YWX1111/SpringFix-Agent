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
- 诊断 Agent 不执行任意 Maven、不执行用户代码，也不修改代码；M5C 只在临时副本
  中运行固定 target test 并由 Surefire XML 判定结果

---

## M3：代码检索增强（已完成）

### 范围

- 检索模块 `src/springfix_agent/retrieval/`：models / tokenizer / chunker / baseline / bm25 / symbol / query_builder / fusion / index / diagnostics
- BM25Okapi 词法检索（rank-bm25 依赖），per-task 内存索引，不持久化
- Java 标识符分词器：camelCase / PascalCase / snake_case / package paths / annotations / exception classes
- Java 代码块切分：regex + brace-depth scanning，fallback 固定窗口（NOT Tree-sitter / AST）
- 符号检索：封装 find_java_symbol
- Reciprocal Rank Fusion：score = Σ weight_i / (k + rank)，k=10，三路等权
- Baseline（M1 词法评分）保留为 fallback 和评测对照
- AgentState 扩展：`retrieval_strategy` / `retrieval_query` / `retrieval_diagnostics`
- 配置扩展：`RETRIEVAL_MAX_FILES` / `RETRIEVAL_MAX_FILE_BYTES` / `RETRIEVAL_MAX_CHUNKS` / `RETRIEVAL_TOP_K` / `RETRIEVAL_CHUNK_MAX_LINES` / `RETRIEVAL_CHUNK_MAX_CHARS` / `RETRIEVAL_CHUNK_OVERLAP_LINES` / `RETRIEVAL_MAX_QUERY_TERMS`
- 检索评测：13 个 case（7 Development + 6 Holdout），Recall@1/3/5、MRR@10、P95 query time
- 评测脚本 `scripts/run_retrieval_eval.py`

### 不做

- Embedding、FAISS、向量检索（后续）
- Tree-sitter AST（后续）
- 新增 LLM 节点（仍为 3 次 LLM 调用）
- SQLite 持久化（M4）
- Agent 准确率评测（M4）

### 验收标准

1. 检索评测脚本可运行并输出 Recall@K / MRR@10 / P95
2. BM25 索引 per-task 构建，不持久化
3. Baseline 可切换，用于评测对照
4. 证据验证规则不变：文件必须在 snippets 中，行号必须在 snippet 范围内
5. 不新增 LLM 调用（仍为 3 次）
6. 263 测试通过，ruff clean，mypy strict clean
7. Live 回归：3 个 case 全部通过

---

## M4：持久化与评测

### M4A：SQLite 持久化与任务重启语义（已完成）

#### 范围

- `SqliteTaskRepository` 实现 `TaskRepository` Protocol
- SQLite Schema：`schema_migrations`、`tasks`、`traces`、`reports`
- 迁移系统：`migrations/001_initial.sql`，幂等、事务、版本记录
- WAL 模式 + busy_timeout 支持并发读和串行写
- 重启遗留任务处理：pending/running 标记为 `interrupted_by_service_restart`
- 配置：`TASK_REPOSITORY=sqlite|memory`，默认 SQLite
- 数据文件：`data/springfix.db`，已被 `.gitignore` 排除
- 48 个新测试覆盖迁移/CRUD/Trace/Report/持久化/并发/重启
- API 路径和 M3 Agent Graph 不变

#### 不做

- LangGraph Checkpoint
- 恢复执行中 Graph
- Redis Stream / Docker 沙箱
- 新 Bug Benchmark（M4B）
- Agent 评测 Runner（M4C）
- 修改 Graph / LLM / Prompt / 检索算法

#### 验收标准

1. SQLite Repository 实现 Protocol 全部方法
2. 迁移幂等、版本记录、失败回滚
3. 重启后历史任务/Trace/报告可查询
4. pending/running 任务重启后标记为 interrupted failure
5. WAL + busy_timeout 支持并发读写
6. 311 测试通过，ruff clean，mypy strict clean
7. API 路径和响应格式不变

### M4B：多 Bug Benchmark（已完成）

#### 范围

- 至少 3 个可复现 Spring Boot Bug 样本
- 三个最小 Spring Boot Bug Sample：事务自调用、Bean 歧义、ConfigurationProperties prefix mismatch
- `benchmark/agent_cases.jsonl` 金标准 Manifest
- `scripts/validate_agent_benchmark.py` Manifest/Gold 校验
- `scripts/verify_benchmark_samples.py` 统一 Maven/Surefire verifier
- Sample README 仅作 Benchmark 文档，不作为 Agent 输入

### M4C：完整 Agent 评测（已完成）

#### 范围

- 评测 Runner `scripts/run_agent_benchmark.py`
- Repository sanitizer、Gold isolation 与 Mock/Live 分离
- 确定性评估指标和脱敏 JSON/Markdown 报告

#### 评测指标

- `issue_category_accuracy`
- `key_file_recall@5`
- `root_cause_hit@1`
- `root_cause_hit@3`
- `average_duration_ms`
- `tool_call_count`
- `llm_call_count`

#### 0.8.0 基线验收

- Mock Benchmark：`3/3`，只验证 Runner/Evaluator/Artifact 链路，不代表模型能力
- Live Benchmark：3 个 Case，模型 `qwen3.7-plus`，`sample_size=3`，均满足项目自定义 `case_pass` 规则
- Gold、Benchmark README/Markdown 和默认 `src/test` 不进入 Agent
- Evidence 经过 deterministic file/line validator；rejected evidence 只衡量无效 repository evidence reference
- 结果不代表生产准确率、Spring Bug 总体准确率或统计显著性；当前没有 LLM Judge
- Token usage 不等于货币成本

#### 不做

- 伪造准确率或命中率数据
- LangSmith / Langfuse 上传
## M5A scope

M5A produces structured Patch Proposals from validated diagnosis evidence. It
supports Mock/Live CLI execution and redacted JSON/Markdown artifacts. It does
not mutate repositories, execute Maven or shell commands, apply patches, or
define Repair Success. Patch Proposal Validation remains an M5A metric; M5C
owns isolated Maven verification and Repair Success.

## M5B scope（0.10.0）

M5B adds `IsolatedPatchWorkspace`、`PatchApplier`、deterministic unified diff
and `PatchApplicationResult`。流程固定为：

```text
source repository -> temporary copy -> full preflight -> apply -> diff -> cleanup
```

M5B 只允许修改已有的 `src/main/java/**` 和 `src/main/resources/**` 文件；禁止新建、
删除或修改 `src/test/**`。复制时保留 `pom.xml`、main code、resources、tests 和配置，
排除 Git metadata、build output、Benchmark/Artifact、Markdown、`.env` 及编译产物。
每次应用前后计算源仓库 allowlist 的 SHA-256 manifest，原仓库新增/删除/修改都会使
`original_repository_unchanged=false`。

所有 Edit 先完成全量 preflight，任何一项失败则整个 Proposal 不写入；同文件 Edit 按
原始行号降序应用，重读临时文件校验 `old_code`，只支持 UTF-8/已有 UTF-8 BOM，保留
newline 和 trailing newline，并通过 sibling temp + flush + `os.replace` 写入。Diff
使用 Python 标准库生成，不调用 `git diff`。

M5B Mock 指标名称是 Patch Application Success，不是 Repair Success。M5B 不执行 Maven、
Gradle、Docker、shell 或网络操作；M5C 才负责隔离副本的 Maven 验证。
## M5C scope (0.11.0)

M5C runs only the fixed-scope `scripts/run_repair_verification.py --mode mock`
flow. It verifies the original Maven Gold failure, reapplies the validated M5A
Mock proposal through M5B, runs the trusted target test in the temporary copy,
and parses Surefire XML for the target counts. It enforces `shell=False`, fixed
Maven arguments, workspace-only cwd, restricted child environment, timeout,
test/pom/source integrity, original-repository integrity, cleanup, and bounded
sanitized artifacts. It has no arbitrary command or argument passthrough, Live
LLM call, automatic repair retry, or OS/container/network sandbox.

## M5D scope (historical, 0.12.0)

M5D is the complete single-shot benchmark composition:

```text
baseline -> sanitized diagnosis -> deterministic diagnosis evaluation
-> proposal -> deterministic validation -> isolated apply
-> restricted Maven/Surefire verification -> funnel and aggregate
```

Mock M5D keeps diagnosis and proposal deterministic while executing real M5B
application and real M5C Maven/Surefire verification. Live M5D runs all three
controlled cases in one Run with one frozen provider/model/config. It records
stage short-circuit outcomes, failure attribution, nullable provider usage,
latency, and redacted artifacts without changing prompts, retrieval, Gold,
sample cases, validators, or the Repair Success definition.
