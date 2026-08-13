# 架构设计（Architecture）

## 1. 系统模块边界

```
┌─────────────────────────────────────────────────────────────┐
│                    前端层 (Vue 3 + TS)                       │ 阶段 2+
│  任务提交 / 诊断结果可视化 / 执行轨迹 / Monaco 报告查看       │
└─────────────────────────────────────────────────────────────┘
                              │ SSE / HTTP
┌─────────────────────────────────────────────────────────────┐
│              Java 业务后端 (Spring Boot 3 + Java 21)         │ 阶段 2+
│  用户/权限(JWT)│ 项目仓库管理│ 任务调度│ SSE 推送│ MinIO 文件│
└─────────────────────────────────────────────────────────────┘
                              │ HTTP / Redis Stream
┌─────────────────────────────────────────────────────────────┐
│              Python Agent 服务 (FastAPI + LangGraph)         │ M0+
│  LangGraph 编排│ Tool 实现│ 检索│ 根因分析│ 报告生成         │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│  存储层: MySQL(业务) + Redis(缓存/Stream) + MinIO(源码/报告) │
│         FAISS(向量检索) + SQLite(Agent 内部 trace)           │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│      验证/沙箱层 (M5C 受限 Maven；Docker Sandbox 后续)       │ M5C / M6+
└─────────────────────────────────────────────────────────────┘
```

M0 阶段仅实现：Python Agent 服务骨架（FastAPI app + 健康检查）+ 长期稳定的 Protocol。

## 2. 接口边界（M0 起定义，后续不动）

### 2.1 Tool Protocol

```python
@runtime_checkable
class Tool(Protocol):
    name: str
    description: str
    def run(self, params: dict, ctx: ToolContext) -> ToolResult: ...
```

### 2.2 TaskRepository Protocol

```python
class TaskRepository(Protocol):
    def create_task(self, ...) -> Task: ...
    def get_task(self, task_id: str) -> Task | None: ...
    def list_tasks(self) -> list[Task]: ...
    def update_status(self, task_id: str, status: TaskStatus) -> None: ...
    def save_trace(self, task_id: str, trace: Trace) -> None: ...
    def get_traces(self, task_id: str) -> list[Trace]: ...
    def save_report(self, task_id: str, report: Report) -> None: ...
    def get_report(self, task_id: str) -> Report | None: ...
```

实现：M1 `InMemoryTaskRepository`，M4A `SqliteTaskRepository`。

### 2.3 Tracer Protocol

```python
class Tracer(Protocol):
    def record_tool_call(self, task_id: str, call: ToolCall) -> None: ...
    def record_node_timing(self, task_id: str, timing: NodeTiming) -> None: ...
    def record_llm_call(self, task_id: str, call: LLMCall) -> None: ...
```

实现：M1 `InMemoryTracer`，M2 扩展 LLM Trace，M4 推送 Redis Stream。

### 2.4 LLMClient Protocol（M2 落地）

```python
class LLMClient(Protocol):
    def invoke_structured(
        self, *,
        system_prompt: str,
        user_prompt: str,
        response_model: type[T],
        trace_context: LLMTraceContext,
    ) -> T: ...
```

实现：M2 `MockLLMClient` + `OpenAICompatibleLLMClient`。

## 3. ToolContext 设计

```python
class ToolContext(TypedDict):
    task_id: str
    repository_path: Path
    allow_root: Path
```

- `allow_root`：系统允许访问的仓库根目录
- `repository_path`：API 层完成 canonicalize 和安全校验后的仓库绝对路径
- Tool 只能读取 `repository_path` 子树
- Tool 参数中不得传入 `repository_path` 或任何绝对路径
- `read_file` 只接收 `relative_path`
- `relative_path` 与 `repository_path` 拼接并 `resolve()` 后，必须仍位于 `repository_path` 内
- `repository_path` 本身必须位于 `allow_root` 内
- 路径校验逻辑统一放在 `tools/_path_safety.py`（M1 创建）

## 4. AgentState 演进策略

不一次性定义包含所有字段的超大 State。按阶段演进：

| 阶段 | 新增字段 |
|------|---------|
| M1 | 输入字段、validate_input 输出、explore_repository 输出、retrieve_code 输出、build_basic_report 输出、tool_calls、node_timings、errors、status、current_node |
| M2 | `issue_analysis`、`investigation_plan`、`root_cause_analysis`、`diagnostic_report`、`llm_calls`、`warnings` |
| M3 | `retrieval_strategy`、`retrieval_query`、`retrieval_diagnostics` |

每次新增字段必须有实际节点使用，不创建纯占位字段。

State 体积限制（M1 起强制）：

- 最多 10 个代码片段
- 每片段最多 60 行
- 每片段最多 4000 字符
- Trace `result_summary` 最多 500 字符
- 不保存完整文件
- State 总体积上限 100KB（初始值，后续根据真实运行数据调整）

## 5. 异步任务边界（M1 起强制）

```python
class TaskService:
    def submit_task(self, repository_path: str, issue_description: str, error_log: str | None) -> str:
        """创建 task_id 并通过进程内后台任务执行"""
        ...

    def run_task_sync(self, task_id: str) -> None:
        """同步执行,用于集成测试与 Graph 调试"""
        ...
```

架构约束（必须在 API 文档和 README 中明示）：

- 这是 MVP 临时方案
- 服务重启会丢失正在运行的任务（M4A 新增中断标记，但不续跑）
- 不支持多实例协调
- M4A 新增 SQLite 持久化，历史任务和报告可在重启后查询
- 后续由 Redis Stream 或任务队列替换

## 6. 工具调用规则（M1 起强制）

- 禁止在 Graph 中硬编码 `symbol_name="saveOrder"` 等样例符号
- `find_java_symbol` 的调用必须从 `error_log` Java 堆栈或 `issue_description` 中提取符号
- 符号提取规则：
  1. 优先从 `error_log` 的 Java 堆栈中提取类名和方法名
  2. 从 `issue_description` 中提取符合 Java 标识符特征的词
  3. 只有提取到明确符号时才调用 `find_java_symbol`
  4. 没有明确符号时跳过该工具
- Graph 必须适用于不同仓库和不同方法名

## 7. 检索评分规则（M1 起强制，M3 多通道增强）

M1 `search_code` 实现简单确定性词法评分（M3 保留为 baseline fallback）：

| 命中类型 | 权重 |
|---------|------|
| 普通关键词命中 | 基础分（1.0） |
| 类名命中 | 加权（2.0） |
| 方法名命中 | 加权（2.0） |
| 异常类名命中 | 加权（3.0） |
| Spring 注解命中 | 加权（2.5） |

- 按总分降序返回 Top K
- 无任何命中时返回空结果

M3 多通道检索管线（`retrieval/` 模块）：

```
AgentState (issue_analysis + investigation_plan)
    │
    ├─► query_builder.py ──► 构建检索查询
    │
    ├─► bm25.py ──► BM25Okapi 词法检索（rank-bm25）    ──┐
    ├─► symbol.py ──► 符号检索（封装 find_java_symbol） ──┤
    ├─► baseline.py ──► M1 词法评分（fallback）          ──┤
    │                                                        │
    └─► fusion.py ──► Reciprocal Rank Fusion (k=10) ◄─────┘
         │
         └─► RetrievalResult (top-K 候选 chunks)
```

- BM25 是**词法检索**（term matching），不是语义检索（无 Embedding / FAISS）
- 索引按任务在内存中构建，不持久化
- Java 标识符分词（`tokenizer.py`）：camelCase / PascalCase / snake_case / package paths / annotations / exception classes
- 代码块切分（`chunker.py`）：regex + brace-depth scanning，fallback 固定窗口；不使用 Tree-sitter / AST
- RRF 融合公式：score = Σ weight_i / (k + rank)，k=10，三路等权

## 8. 示例 Bug 复现方式（M1 起强制）

示例事务 Bug 必须满足：

- 框架：Spring Boot + Spring Data JPA 或 JdbcTemplate + H2 内存数据库 + JUnit 5 + Spring Boot Test
- Bug 类型：同类内部调用绕过 Spring AOP 代理，导致 `@Transactional` 不生效
- 必须包含一个可独立运行的失败测试：`mvn test`
- 测试过程：
  1. 外部调用一个未加事务的方法
  2. 该方法通过 `this` 或直接方法调用，调用同类中带 `@Transactional` 的方法
  3. 内部方法写入数据库后抛出 `RuntimeException`
  4. 由于自调用绕过代理，预期的事务没有生效
  5. 测试通过数据库记录数量证明数据未按预期回滚
- sample README 必须记录：Bug 描述、预期行为、实际行为、根因、复现命令、预期失败测试名称
- 诊断 Agent 不执行 Maven；M4B/M5C 只由固定脚本执行受限的基准验证
- M5C 在临时隔离副本中运行固定 target test，不提供 Docker/OS/network sandbox

## 9. 最终技术栈

### 前端（阶段 2+）

Vue 3、TypeScript、Vite、Element Plus、Pinia、Axios、SSE、Monaco Editor

### Java 业务后端（阶段 2+）

Java 21、Spring Boot 3、Spring MVC、MyBatis-Plus、MySQL、Redis、Redis Stream、Spring Security、JWT、SSE、MinIO

### Python Agent 服务（M0+）

Python 3.11+、FastAPI、Pydantic、Pydantic-Settings、Uvicorn、LangGraph（M1+）、HTTPX（M2 Live）、rank-bm25（M3+）、SQLite 标准库（M4A+）、FAISS / Tree-sitter / GitPython（后续）、Docker SDK（阶段 3+）

### 部署（阶段 4+）

Docker Compose、Nginx、MySQL、Redis、MinIO

## 10. M1.1 阶段基线固化（已完成）

M1.1 不新增任何 Agent 能力，仅处理质量、CI 和可复现性：

| 项 | 实现 |
|----|------|
| 统一请求校验错误 | `RequestValidationError` handler 返回 `{error: "request_validation_error", message, details[{field, reason}]}` |
| 示例 Bug 验证脚本 | `scripts/verify_sample_bug.py` 跨平台执行 `mvn test`，断言事务目标失败签名，保持兼容 |
| M4B Sample 验证 | `scripts/verify_benchmark_samples.py` 读取 Manifest，执行三个 Maven Sample 并校验 Surefire 金标准 |
| Manifest 校验 | `scripts/validate_agent_benchmark.py` 校验相对路径、文件、符号、Evidence 行号和测试名 |
| GitHub Actions | `.github/workflows/ci.yml`：`python-quality`（Python 3.11 + uv）+ benchmark sample verification（Java 21 + Maven） |
| Warning 过滤 | StarletteDeprecationWarning 用 message 正则限定，而非整个类别 |
| LangGraph type ignore | 4 处 `# type: ignore[call-overload]` 保留并加说明（langgraph 0.2 类型签名未稳定） |
| 符号链接测试 | Windows 本地跳过；Linux CI 必须执行，被跳过视为配置问题 |

## 11. M2 阶段 LLM 推理节点（已完成）

M2 在 M1 确定性工作流基础上新增 3 个 LLM 节点：

| 节点 | 类型 | 输入 | 输出 | 降级策略 |
|------|------|------|------|---------|
| `issue_parser` | LLM | issue_description, error_log | IssueAnalysis | 用 M1 确定性符号提取，category=unknown |
| `task_planner` | LLM | issue_analysis, issue_description | InvestigationPlan (3-6 步) | 用确定性最小排查计划 |
| `root_cause_analyzer` | LLM | snippets, issue_analysis, plan | RootCauseAnalysis | 输出 insufficient_evidence |

### LLM 客户端抽象

```python
class LLMClient(Protocol):
    def invoke_structured(
        self, *,
        system_prompt: str,
        user_prompt: str,
        response_model: type[T],
        trace_context: LLMTraceContext,
    ) -> T: ...
```

- `MockLLMClient`：测试 / CI / 离线开发，不需要 API Key
- `OpenAICompatibleLLMClient`：真实模型，httpx 实现，OpenAI 兼容端点
- LLM_PROVIDER 切换：`mock` / `openai_compatible`

### 结构化输出 Schema

- `IssueAnalysis`：issue_category / summary / symptoms / exception_types / extracted_symbols / search_terms / spring_concepts
- `InvestigationPlan`：3-6 个 InvestigationStep，step_id 严格递增
- `RootCauseAnalysis`：diagnosis_status (complete / partial / insufficient_evidence) + 最多 3 个 RootCauseCandidate
- 每个候选必须引用 retrieved_snippets 中真实存在的文件和行号

### 超时与重试

仅重试：网络超时 / 连接失败 / 429 / 5xx / 首次 Schema 校验失败（一次格式修复）

不重试：401 / 403 / 配置缺失 / 持续 Schema 校验失败 / Prompt 逻辑错误

所有重试有最大次数（默认 2），记录 attempt，不形成无限循环。

### Prompt 管理

- 模板存放在 `llm/prompts/*.md`，独立于 Python 代码
- 每个 Prompt 明确：角色 / 输入边界 / 输出 Schema / 禁止编造 / 证据不足处理 / 长度约束 / 禁止项
- 不要求模型输出隐藏思维链
- Prompt Injection 防护：代码 / 注释 / README / 日志视为数据，嵌入式指令不执行

### LLM Trace

每次 LLM 调用记录：

- node_name / provider / model / attempt
- start / end / duration_ms（单调时钟）
- status (success / retry / error)
- prompt_chars / response_chars（字符数，不保存正文）
- input_tokens / output_tokens（模型返回时记录，否则 null）
- error_type / error_message（长度限制 500 字符）
- 永不保存 API Key / 完整 Prompt / 完整响应

API traces 响应区分 `node_traces` / `tool_traces` / `llm_traces`。

### Live 模式

`scripts/run_live_diagnosis.py`：

- 参数：`--repository` / `--issue` / `--error-log-file` / `--output`
- 从环境变量读取模型配置
- 缺少配置时清晰失败
- 输出 task_id / diagnosis_status / LLM 调用次数 / 耗时 / Token
- 永不输出 API Key
- 普通 CI 不运行该脚本

三个真实模型 Live Case 已完成回归。它们不构成准确率评测；Prompt Injection
Case 只验证当前防护设计和一次模型行为，不代表绝对安全。

### M2 运行边界

- 检索已升级为 M3 多通道（BM25 + 符号 + baseline + RRF）
- 任务与 Trace 使用 `SqliteTaskRepository`（默认）或 `InMemoryTaskRepository`
- 后台任务使用进程内 `threading.Thread`
- M4A 新增 SQLite 持久化，重启后历史可查，执行中任务标记中断
- Agent 不执行 Maven、不执行用户代码，也不修改代码

## M4C 基线（0.8.0）

M4C 的 Benchmark Runner 在每个 Case 前创建临时 Repository View，默认排除
README/Markdown、`src/test`、`target`、`.git`、`benchmark` 和 `artifacts`，并在
评估完成后清理临时目录。Agent-facing 输入严格限定为 `repository`、
`issue_description` 和 `error_log`；Gold 只由执行后的 deterministic evaluator 使用。

Mock Benchmark 固定为 3 个 Case，验收结果为 `3/3`，只验证 Runner/Evaluator/Artifact
链路，不代表模型能力。0.8.0 Live 基线使用 `qwen3.7-plus`，`sample_size=3`，三个
Case 均满足项目自定义 `case_pass` 工程规则。Evidence 必须通过确定性文件/行号
校验；rejected evidence 只表示无效 repository evidence reference，不等同于全部
事实幻觉。Live 只保存脱敏结构化结果，不保存 API Key、完整 Prompt、raw response
或本机路径；当前没有 LLM Judge，Token usage 也不等于货币成本。

## 14. M4A 阶段 SQLite 持久化（已完成）

M4A 新增 SQLite 存储层：

| 文件 | 职责 |
|------|------|
| `storage/sqlite_repository.py` | SQLite 实现 `TaskRepository` Protocol |
| `storage/migration.py` | 最小迁移系统（幂等、事务、版本记录） |
| `storage/migrations/001_initial.sql` | 初始 Schema（四张表） |

关键约束：

- 使用 Python 标准库 `sqlite3`，不引入 SQLAlchemy / Alembic
- WAL 模式 + busy_timeout 支持并发读和串行写
- 每个操作开独立连接，不跨线程复用
- foreign_keys 强制开启
- 参数化 SQL，禁止字符串拼接
- 重启遗留任务处理：pending/running → failed + `interrupted_by_service_restart`
- 不实现 LangGraph Checkpoint，不恢复执行中 Graph
- SQLite 适用于本地单机 MVP，不代表生产数据库方案

## 12. M0 阶段技术栈（精简）

仅引入：

- FastAPI（Web 框架）
- Uvicorn（ASGI 服务器）
- Pydantic（数据模型）
- Pydantic-Settings（配置管理）
- HTTPX（测试客户端）
- Pytest（测试框架）
- Ruff（代码检查）
- MyPy（静态类型检查）

不引入：LangGraph、LangChain、Anthropic SDK、OpenAI SDK、rank_bm25、FAISS、Tree-sitter、SQLAlchemy、Redis、MinIO、Docker SDK。

## 13. M3 阶段代码检索增强（已完成）

M3 新增 `src/springfix_agent/retrieval/` 模块，实现多通道代码检索：

| 文件 | 职责 |
|------|------|
| `models.py` | 检索领域模型（Chunk / RetrievalResult / RetrievalDiagnostics） |
| `tokenizer.py` | Java 标识符分词器 |
| `chunker.py` | Java 代码块切分（regex + brace-depth） |
| `baseline.py` | M1 词法评分（fallback + 评测对照） |
| `bm25.py` | BM25Okapi 词法检索 |
| `symbol.py` | 符号检索（封装 find_java_symbol） |
| `query_builder.py` | 从 AgentState 构建查询 |
| `fusion.py` | Reciprocal Rank Fusion（k=10） |
| `index.py` | BM25 索引管理 |
| `diagnostics.py` | 检索诊断信息 |

关键约束：

- BM25 是词法检索，不是语义检索
- 索引 per-task 内存构建，不持久化
- 不新增 LLM 节点，不增加 LLM 调用次数
- 代码块切分使用 regex + brace-depth scanning，不使用 Tree-sitter
## M5A Repair Proposal layer

```text
completed diagnostic task
  -> validated RootCauseAnalysis
  -> deterministic validated evidence + real source ranges
  -> PatchProposalGenerator (one independent LLM call)
  -> PatchProposalValidator
  -> review-only proposal artifact
```

The layer is outside the seven-node Graph. It enforces production path
allowlisting, evidence overlap, real `old_code` matching, dangerous-code
checks, duplicate/conflict checks, and rejected-edit auditing. It never writes
repository files or executes Maven.

## M5B Isolated Patch Application layer

M5B remains outside the seven-node Diagnostic Graph:

```text
validated PatchProposal
  -> IsolatedPatchWorkspace (source copy + SHA-256 manifest)
  -> PatchApplier (full preflight, then deterministic writes)
  -> Python unified diff
  -> PatchApplicationResult
```

`IsolatedPatchWorkspace` copies the Maven project structure, including
`pom.xml`, `src/main`, `src/test`, resources, and configuration files. It
excludes `.git`, `target`, `build`, `node_modules`, `artifacts`, `benchmark`,
`__pycache__`, compiled/archive/log files, `.env`, and Markdown/README files.
The source manifest is computed before the copy and after application; a
changed, added, or deleted copied-range file fails the application integrity
result. The context manager cleans the temporary directory in `finally`.

`PatchApplier` accepts only a `PatchValidationResult` that passed M5A. It
re-reads the temporary file, checks allowed production paths, exact original
line ranges, old-code freshness, UTF-8/BOM encoding, duplicate/overlap
conflicts, and non-empty changes before writing anything. The default policy is
all-or-nothing. Same-file edits are applied from the highest original line to
the lowest so earlier edits cannot shift later ranges. `src/test/**` is copied
for later M5C use but is never an allowed application target.

Diffs use Python `difflib.unified_diff` with repository-relative `a/` and `b/`
paths. M5B records Patch Application Success metrics only; it does not run
Maven and does not claim Repair Success. M5C is the deterministic Maven
verification stage on the patched copy.

## M5C Isolated Maven Repair Verification layer

```text
benchmark baseline Gold
  -> validated M5A Mock proposal
  -> M5B temporary workspace + deterministic application
  -> test/pom/source integrity checks
  -> fixed Maven target selector with shell=False
  -> Surefire XML target-test oracle
  -> structured RepairVerificationResult + sanitized artifact
```

`MavenRepairVerifier` owns JDK/Maven discovery, the trusted target selector,
restricted subprocess environment, timeout and bounded output tails. It never
accepts a user command or arbitrary argument list. The patched Maven cwd must
be the active temporary workspace and never the source repository. The child
environment keeps only launch/runtime fields needed by Maven/JDK and removes
LLM credentials, API keys, tokens, secrets, authorization, and inherited Maven
injection options.

Before the patched invocation, M5C verifies the original bug against the
manifest-declared failure counts and terms. It then checks that `src/test/**`,
`pom.xml`, and all non-proposal source files are unchanged. After Maven,
Surefire XML reports for the exact target test are selected; unrelated test
reports cannot make a case pass. Repair Success requires baseline reproduction,
validated/all-edits-applied patch, source/test/pom and source-repository
integrity, target execution, Maven exit `0`, `tests>0`, and zero failures,
errors, or skips. M5C is process-restricted verification, not an OS,
container, or network sandbox.

## M5D Single-shot End-to-End Benchmark layer

```text
M4C Diagnostic Graph -> M4C evaluator -> M5A proposal/validator
-> M5B isolated applier -> M5C Maven/Surefire verifier
-> per-case attribution + Run funnel/aggregate
```

M5D is orchestration and measurement, not new intelligence. Baseline Maven
Gold gates each case before model calls. The Agent receives only the sanitized
repository and the existing three-field input. Repair Gold is loaded only
after model outputs for deterministic post-run evaluation. One Live Run uses
one frozen provider/model/config across all cases. Failures stop that case,
remain in aggregate denominators, and are never automatically repaired again.

The formal M5D Live baseline is Run `20260812T040246Z-b5818c80`: diagnosis
completed and passed 3/3, proposal and application reached 2/3, target tests
executed 1/3, and single-shot Repair Success was 1/3. The bean ambiguity case
failed before a valid target Surefire result was produced; the config-prefix
case passed; no result was retried or optimized after the Run.

## M6A RCA and M6B Repair Observability Hardening

M6A preserves the retained M5D Live Run postmortem under
`artifacts/failure-analysis/m5d-live-20260812T040246Z-b5818c80/`. It records
the evidence boundary and failure attribution without changing the historical
run or presenting it as a Repair Success improvement.

M6B stores bounded proposal-generation audit data in the existing LLM trace
payload and proposal result artifacts. The audit distinguishes logical call,
HTTP attempts, provider completion, response receipt/count, structured parse,
schema validation, generator outcome, and stable failure category/detail. It
never stores prompt or response bodies. Maven verification adds deterministic
lifecycle/failure classification, tri-state `surefire_started`, first
actionable error, and repository-relative file/symbol fields. These are
observability-only additions; repair generation, application, validation, and
success gates remain unchanged.

## M6C-2 Import-aware Patch Correctness

M6C-2 is a generic Java-level correctness layer after the existing M5A
Evidence Gate. The Patch Prompt requires a Proposal that introduces a new
simple Java type or annotation to include its import in the same Java file,
without wildcard imports or case-specific examples. The validator does not
auto-edit a Proposal and does not start a retry loop.

`repair/java_import_validator.py` performs a bounded heuristic over the
existing full Java file and the composed proposed file. It recognizes
high-confidence annotation/type contexts, subtracts Java keywords,
`java.lang` common types, same-file declarations, existing imports, and
fully-qualified names, and reports `pass`, `fail`, or conservative `unknown`.
It does not implement Java name resolution or a parser/frontend.

`missing_required_import` rejects a high-confidence unresolved symbol and
records `affected_symbol`. A supporting import edit is a derived exception to
the unchanged Evidence Gate only when it shares an evidence-supported
`src/main/java/**` file with a primary edit, is located in the Java import
section, changes only import declarations, and imports a symbol used by that
primary edit. Unrelated imports and unsupported import-only edits are rejected.
Maven remains the authoritative compile/test oracle; the import check only
catches obvious incomplete proposals earlier.
