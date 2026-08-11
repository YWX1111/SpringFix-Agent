# 项目级开发约束（SpringFix Agent）

> 本文件仅约束 SpringFix Agent 项目内的开发，不覆盖工作站上的全局配置。

## 阶段定位

当前阶段：**M5A 结构化 Patch Proposal（已完成）**；版本 0.9.0。

M4A 在 M3 基础上新增 SQLite 持久化层：

- `SqliteTaskRepository` 实现 `TaskRepository` Protocol
- SQLite Schema：`schema_migrations`、`tasks`、`traces`、`reports` 四张表
- 迁移系统：`migrations/001_initial.sql`，幂等、事务、版本记录
- WAL 模式 + busy_timeout 支持并发读和串行写
- 重启遗留任务处理：pending/running 标记为 `interrupted_by_service_restart`
- 配置：`TASK_REPOSITORY=sqlite|memory`，默认 SQLite
- `InMemoryTaskRepository` 继续保留
- API 路径和 M3 Agent Graph 不变
- 不实现 LangGraph Checkpoint，不恢复执行中 Graph
- SQLite 适用于本地单机 MVP，不代表生产数据库方案
- 311 测试通过（+48），ruff clean，mypy strict clean

M4A 不包含：
- M4C 完整 Agent 评测
- Redis Stream / Docker 沙箱
- 修改七节点 Graph / LLM / Prompt / 检索算法

M3 范围内已完成（M4A 保留）：

- 检索模块（`retrieval/`）：
  - `models.py`（检索领域模型：Chunk / RetrievalResult / RetrievalDiagnostics 等）
  - `tokenizer.py`（Java 标识符分词器：camelCase / PascalCase / snake_case / package paths / annotations / exception classes）
  - `chunker.py`（Java 代码块切分：regex + brace-depth scanning，fallback 到固定窗口；NOT Tree-sitter / AST）
  - `baseline.py`（M1 词法评分保留为 fallback 和评测对照）
  - `bm25.py`（BM25Okapi 词法检索，rank-bm25 依赖；按任务在内存中建索引，不持久化）
  - `symbol.py`（符号检索，封装 find_java_symbol）
  - `query_builder.py`（从 AgentState 构建检索查询）
  - `fusion.py`（Reciprocal Rank Fusion：score = Σ weight_i / (k + rank)，k=10）
  - `index.py`（BM25 索引管理，per-task 内存索引）
  - `diagnostics.py`（检索诊断信息收集）
- AgentState 扩展：`retrieval_strategy` / `retrieval_query` / `retrieval_diagnostics`
- 配置扩展：`RETRIEVAL_MAX_FILES=200` / `RETRIEVAL_MAX_FILE_BYTES=200000` / `RETRIEVAL_MAX_CHUNKS=1000` / `RETRIEVAL_TOP_K=10` / `RETRIEVAL_CHUNK_MAX_LINES=60` / `RETRIEVAL_CHUNK_MAX_CHARS=4000` / `RETRIEVAL_CHUNK_OVERLAP_LINES=5` / `RETRIEVAL_MAX_QUERY_TERMS=50`
- 检索评测：13 个 case（7 Development + 6 Holdout，`tests/fixtures/retrieval/benchmark/retrieval_cases.jsonl`），脚本 `scripts/run_retrieval_eval.py`
- 评测指标：Recall@1/3/5、MRR@10、P95 query time（检索指标，非 Agent 准确率）
- 263 测试通过，ruff clean，mypy strict clean
- Live 回归：3 个 case 全部通过，每个 3 次 LLM 调用
- M4A 新增 48 个测试，共 311 个

**检索评测说明**：
- Symbol 通道的部分输入来自模拟的 `IssueAnalysis.extracted_symbols`，属于 enriched-query retrieval
- `expected_symbols` 只作为金标，不进入 `RetrievalQuery`
- 当前评测主要是相关文件级 Recall/MRR；方法块、行号和证据片段级排序质量尚未被完整量化
- 后续完整评测可增加 Evidence Hit@K、Relevant Line Range Recall@K 和 First Relevant Chunk Rank
- Hybrid 的定位是提高 Top-K 召回完整性，不代表全面提升 Top-1 排序
- `k=10`、三路等权是在当前指标全部相同情况下选择的简单配置，不是大规模调优结果
- BM25 是词法检索，不是语义检索
- 当前 Benchmark 样本规模小，不代表生产环境召回率或 Agent 根因准确率

M2 范围内已完成（M3 保留）：

- 7 节点 LangGraph：
  - `validate_input`（确定性）
  - `issue_parser`（LLM）
  - `task_planner`（LLM）
  - `explore_repository`（确定性，合并 LLM 符号）
  - `retrieve_code`（确定性，查询来源扩展）
  - `root_cause_analyzer`（LLM，二次业务校验）
  - `build_diagnostic_report`（确定性，区分 diagnosis_status）
- LLM 层（`llm/`）：
  - `client.py`（LLMClient Protocol + LLMTraceContext）
  - `mock.py`（MockLLMClient，测试 / CI / 离线开发）
  - `openai_compatible.py`（OpenAI 兼容客户端，httpx 实现）
  - `schemas.py`（IssueAnalysis / InvestigationPlan / RootCauseAnalysis）
  - `parser.py`（结构化解析 + 一次格式修复）
  - `_retry.py`（bounded retry，仅重试可重试错误）
  - `trace.py`（LLMCall TypedDict）
  - `prompts/`（.md 模板，独立于 Python 代码）
- AgentState 扩展：`issue_analysis` / `investigation_plan` / `root_cause_analysis` / `diagnostic_report` / `llm_calls` / `warnings`
- Tracer 扩展：`record_llm_call`，Trace.kind 支持 `llm_call`
- API 扩展：traces 响应区分 `node_traces` / `tool_traces` / `llm_traces`
- Live 诊断脚本：`scripts/run_live_diagnosis.py`
- 配置扩展：`LLM_PROVIDER` / `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` 等
- 测试数量以当前完整回归结果为准；Windows 符号链接用例可能因权限跳过，Linux CI 必须实际执行
- 三个真实模型 Live Case 已完成回归，但该样本不代表准确率
- Prompt Injection Case 只验证当前防护设计和一次模型行为，不代表绝对安全

M1 范围内已完成（M2 保留）：

- 文档：README、本文件、product-requirements、architecture、mvp-scope、development-roadmap、evaluation-design、decisions/0001-mvp-first
- 工程骨架：pyproject.toml、.gitignore、.env.example
- API 层：`/api/v1/health`、`/api/v1/tasks`（POST/GET）、`/tasks/{id}/traces`、`/tasks/{id}/report`
- 工具层（`tools/`）：`base.py`、`_path_safety.py`、`_java_patterns.py`、`_invoker.py`、`list_project_tree.py`、`search_code.py`、`read_file.py`、`find_java_symbol.py`
- 存储层（`storage/`）：`models.py`、`repository.py`、`in_memory.py`
- 可观测层（`observability/`）：`tracer.py`、`in_memory_tracer.py`
- 服务层（`service/`）：`task_service.py`（M2 接受 LLMClient）
- 示例 Bug 项目：`samples/sample-springboot-bug-transaction-self-invocation`

M1.1 基线固化（M2 保留）：

- 统一请求校验错误：`RequestValidationError` 返回结构化 JSON
- 示例 Bug 验证脚本：`scripts/verify_sample_bug.py`（保持兼容）
- M4B 统一 Sample 验证：`scripts/verify_benchmark_samples.py`
- Benchmark Manifest 校验：`scripts/validate_agent_benchmark.py`
- GitHub Actions：`.github/workflows/ci.yml`（python-quality + benchmark sample verification）
- Warning 过滤收窄：StarletteDeprecationWarning 用 message 限定
- LangGraph type ignore：7 处 `# type: ignore[call-overload]` 保留并加说明
- 符号链接测试说明：Windows 本地跳过；Linux CI 必须执行

## M4A 禁止创建（M4A 已实现 SQLite 持久化）

- 新 Bug Benchmark → 推迟到 M4B
- Agent 评测 Runner → 推迟到 M4C
- Embedding / FAISS / 向量检索 → 推迟到后续里程碑
- Tree-sitter AST → 推迟到后续里程碑
- LangGraph Checkpoint → 推迟到后续里程碑
- Redis Stream → 推迟到后续里程碑
- Vue 前端 / Spring Boot 后端 / MySQL / Redis / MinIO → 推迟到阶段 2+
- Docker 沙箱 / Maven 测试执行 / 自动代码修改 → 推迟到阶段 3+
- 多 Agent / 循环 / Reflection → 推迟到阶段 3+
- 任何 `raise NotImplementedError` 的占位实现文件

## M4C Benchmark 约束

- `benchmark/repository_view.py` 在每个 Case 前创建临时安全副本；原 Sample 不传入 Graph。
- Agent 输入严格只有 `repository`、`issue_description`、`error_log`；Gold 字段只能在 evaluator 中使用。
- 默认排除 README/Markdown、target、.git、benchmark、artifacts 和 `src/test`；`--include-tests` 仅是单独实验模式。
- Runner 不修改 Sample，不执行 Maven，不执行自动修复，不扩展 Graph/Prompt/SQLite schema。
- Mock 与 Live artifact 分目录；Live 只保存脱敏结构化结果，不保存 raw response、完整 Prompt、API Key 或绝对路径。
- `case_pass` 是项目工作流验收规则，不称为生产准确率；3 个 Case 必须标记 `sample_size=3`。
- Token usage 只接受 provider 返回值；缺失时写 `null`，不估算成本。

M4C 0.8.0 已固化：Mock `3/3`；Live 使用 `qwen3.7-plus`，三个 Case 均满足
项目自定义 `case_pass` 规则。该结果不代表生产准确率或统计显著性；当前没有
LLM Judge。`rejected_evidence` 仅衡量被确定性文件/行号校验拒绝的 repository
evidence reference，不描述模型全部事实幻觉；Token usage 不等于货币成本。

## 代码规范

- Python 3.11+ 语法（本地开发环境为 3.13，CI 需兼容 3.11）
- Ruff 必须通过：`uv run ruff check src/ tests/`
- MyPy strict 必须通过：`uv run mypy --strict src/`
- Pytest 必须通过：`uv run pytest tests/ -v`
- 类型注解强制：所有公开函数必须有完整类型签名
- 不写注释解释 WHAT，只在 WHY 非显然时写一行注释
- 不创建未使用的空文件
- 不输出伪造的测试结果或准确率数据

## ToolContext 设计约束（M1 起强制）

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
- 路径校验逻辑统一放在 `tools/_path_safety.py`

## AgentState 演进策略

不一次性定义包含 M1/M2/M3 全部字段的超大 State。按阶段演进：

- M1：已定义确定性工作流需要的 AgentState（task_id, repository_path, issue_description, error_log, validation_ok, validation_errors, extracted_symbols, project_tree_summary, candidate_files, retrieved_snippets, retrieval_summary, basic_report, markdown_report, tool_calls, node_timings, errors, status, current_node）
- M2：加入 `issue_analysis`、`investigation_plan`、`root_cause_analysis`、`diagnostic_report`、`llm_calls`、`warnings`
- M3：加入 `retrieval_strategy`、`retrieval_query`、`retrieval_diagnostics`

每次新增字段必须有实际节点使用，不创建纯占位字段。

State 体积限制（M1 起强制）：

- 最多 10 个代码片段
- 每片段最多 60 行
- 每片段最多 4000 字符
- Trace `result_summary` 最多 500 字符
- 不保存完整文件
- State 总体积上限 100KB（初始值，后续根据真实运行数据调整，不宣传为已验证最佳值）

## 异步任务边界（M1 起强制）

- `TaskService.run_task_sync(task_id)`：同步执行，用于集成测试与 Graph 调试
- `TaskService.submit_task(...)`：创建 task_id 并通过进程内后台任务执行

架构文档必须明确：

- 这是 MVP 临时方案
- 服务重启会丢失正在运行的任务
- 不支持多实例协调
- 后续由 Redis Stream 或任务队列替换

## 工具调用规则（M1 起强制）

- 禁止在 Graph 中硬编码 `symbol_name="saveOrder"` 等样例符号
- `find_java_symbol` 的调用必须从 `error_log` Java 堆栈或 `issue_description` 中提取符号（`_symbol_extraction.py`）
- 没有明确符号时跳过该工具，不伪造候选
- Graph 必须适用于不同仓库和不同方法名

## 检索评分规则（M1 起强制，M3 多通道增强）

M1 `search_code` 实现简单确定性词法评分（M3 保留为 baseline fallback）：

- 普通关键词命中：加基础分
- 类名、方法名命中（lowerCamelCase / UpperCamelCase）：提高权重
- 异常类名命中（...Exception）：提高权重
- Spring 注解命中（@...）：提高权重
- 按总分降序返回 Top K
- 无任何命中时返回空结果

M3 多通道检索（`retrieval/` 模块）：

- BM25（`bm25.py`）：rank-bm25 BM25Okapi，**词法检索**而非语义检索；per-task 内存索引，不持久化
- 符号检索（`symbol.py`）：封装 find_java_symbol，基于 LLM 提取的符号
- Baseline（`baseline.py`）：M1 词法评分，保留为 fallback 和评测对照
- RRF 融合（`fusion.py`）：Reciprocal Rank Fusion，score = Σ weight_i / (k + rank)，k=10
- Java 分词（`tokenizer.py`）：camelCase / PascalCase / snake_case / package paths / annotations / exception classes
- 代码块切分（`chunker.py`）：regex + brace-depth scanning，fallback 固定窗口；不使用 Tree-sitter

## 评测指标（M4 落地，M1 仅落盘设计）

保留 7 个指标定义：

- `issue_category_accuracy`
- `key_file_recall@5`
- `root_cause_hit@1`
- `root_cause_hit@3`
- `average_duration_ms`
- `tool_call_count`
- `llm_call_count`

M1-M3 期间不输出 Agent 准确率或命中率。M3 检索评测（Recall@K / MRR / P95）是检索质量指标，不等于 Agent 准确率。M4C Agent 评测脚本为 `scripts/run_agent_benchmark.py`。

## Git 策略

- M0/M1/M1.1/M2/M3/M4A 已完成基线固化并提交 Git

## 阶段切换准则

进入下一里程碑的前提：

1. 当前里程碑所有验收标准通过（ruff + mypy strict + pytest + 实际启动验证 + 示例 Bug Maven 预期失败验证 + verify_sample_bug.py 通过）
2. 没有创建任何下一里程碑的提前实现文件
3. 用户明确确认"进入下一里程碑"
## M5A Patch Proposal boundary

Version `0.9.0` adds an independent `repair/` stage after the unchanged
diagnostic Graph. The three diagnostic LLM calls remain unchanged; M5A adds
one Patch LLM call only after validated RootCauseAnalysis and deterministic
file/line evidence are available.

The service and CLI create review artifacts only. They never modify samples,
run Maven, execute shell commands, apply a proposal, or add a SQLite schema.
The validator checks production paths, evidence overlap, true `old_code`,
dangerous `new_code`, duplicate edits, and conflicts. M5B Sandbox and M5C
Maven verification remain later milestones.
