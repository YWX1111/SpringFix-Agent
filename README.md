# SpringFix Agent

面向 Java/Spring Boot 项目的智能故障诊断与修复平台。

> 面向 Agent 应用开发岗位面试的个人项目。核心不在产品形态，而在体现 LangGraph 状态编排、Tool Calling、多步骤规划、Java 代码混合检索、Agent 可观测性、Agent 评测、Java/Python 双服务协作等工程能力。

## 当前阶段

**M4C（完整 Agent Benchmark Runner）** 已完成。M4A 的 SQLite 持久化和 M4B 的三个故意失败 Sample 保持不变，本轮新增隔离型 Repository View、Mock/Live Runner、确定性 evaluator/metrics 和脱敏报告。

M4A 产出：

- `SqliteTaskRepository` 实现 `TaskRepository` Protocol
- SQLite Schema 与迁移系统（`migrations/001_initial.sql`）
- 四张表：`schema_migrations`、`tasks`、`traces`、`reports`
- WAL 模式 + busy_timeout 支持并发读和串行写
- 重启遗留任务处理：pending/running 标记为 `interrupted_by_service_restart`
- 历史任务和结果可在重启后查询，但执行中的任务不能续跑
- 配置：`TASK_REPOSITORY=sqlite|memory`，默认 SQLite
- 数据文件：`data/springfix.db`，已被 `.gitignore` 排除
- 311 测试通过（+48），ruff clean，mypy strict clean

**M4A 边界说明**：
- SQLite 适用于本地单机 MVP，不代表生产数据库方案
- 当前没有 LangGraph Checkpoint，执行中的 Graph 不能续跑
- 当前没有 Redis Stream，仍为进程内后台线程
- M4B 已增加三个故意失败的 Bug Benchmark Sample；M4C 才进行完整 Agent 评测
- M4C Runner 默认使用 Mock，Live 模式必须显式配置 OpenAI-compatible provider

M3 产出（M4A 保留）：

- 7 节点 LangGraph：`validate_input → issue_parser → task_planner → explore_repository → retrieve_code → root_cause_analyzer → build_diagnostic_report`
- 3 个 LLM 节点（IssueParser / TaskPlanner / RootCauseAnalyzer）
- LLM 客户端抽象（Protocol + MockLLMClient + OpenAICompatibleLLMClient）
- Pydantic 结构化输出校验
- 超时 / 重试 / 降级策略
- Prompt 模板（.md 文件，独立于 Python 代码）
- Prompt Injection 防护规则与回归测试（不代表绝对安全）
- LLM Trace（独立于 Tool Trace / Node Trace）
- Live 诊断脚本 `scripts/run_live_diagnosis.py`
- 默认 Mock 模式，无 API Key 也能运行全部测试

M2 不包含（M3 已实现）：

- ~~BM25 词法检索~~（M3 ✅）
- Embedding / FAISS / Tree-sitter（后续）
- SQLite 持久化（M4）
- Vue 前端 / Spring Boot 后端
- Docker 沙箱 / Maven 自动测试 / 自动代码修改
- 多 Agent / 反思 / 循环

M3 产出：

- 检索模块 `retrieval/`：BM25（词法检索）、Java 标识符分词、代码块切分、符号检索、RRF 融合
- BM25 per-task 内存索引，不持久化
- Baseline（M1 词法评分）保留为 fallback 和评测对照
- AgentState 扩展：`retrieval_strategy` / `retrieval_query` / `retrieval_diagnostics`
- 检索评测：13 个 case（7 Development + 6 Holdout），Recall@1/3/5、MRR@10、P95 query time
- 评测脚本 `scripts/run_retrieval_eval.py`
- 不新增 LLM 节点（仍为 3 次 LLM 调用）
- 263 测试通过，ruff clean，mypy strict clean

**评测说明**：
- Symbol 通道的部分输入来自模拟的 `IssueAnalysis.extracted_symbols`，属于 enriched-query retrieval，不完全等同于仅使用原始用户问题的检索效果
- `expected_symbols` 只作为金标，不进入 `RetrievalQuery`
- 当前评测主要是相关文件级 Recall/MRR；方法块、行号和证据片段级排序质量尚未被完整量化
- 后续完整评测可增加 Evidence Hit@K、Relevant Line Range Recall@K 和 First Relevant Chunk Rank
- Hybrid 的定位是提高 Top-K 召回完整性，不代表全面提升 Top-1 排序
- Development 用于有限参数选择，Holdout 只用于冻结后的验证
- `k=10`、三路等权是在当前指标全部相同情况下选择的简单配置，不是大规模调优结果
- BM25 是词法检索，不是语义检索
- 当前 Benchmark 样本规模小（13 case），不代表生产环境召回率或 Agent 根因准确率

## 启动方法

### Windows PowerShell

```powershell
uv sync --extra dev
.\scripts\run_dev.ps1
```

### WSL / Linux / macOS

```bash
uv sync --extra dev
./scripts/run_dev.sh
```

默认 LLM_PROVIDER=mock，无需 API Key 即可启动。访问：

- 健康检查：`GET http://localhost:8000/api/v1/health`
- OpenAPI 文档：`GET http://localhost:8000/docs`

## 验证命令

```powershell
uv run ruff check src/ tests/ scripts/
uv run mypy --strict src/
uv run pytest tests/ -v
uv run python scripts/verify_sample_bug.py
uv run python scripts/verify_benchmark_samples.py
uv run python scripts/validate_agent_benchmark.py
uv run python scripts/run_retrieval_eval.py  # M3 检索评测
uv run python scripts/run_agent_benchmark.py --mode mock
```

### M4C Agent Benchmark

```powershell
uv run python scripts/run_agent_benchmark.py --mode mock
uv run python scripts/run_agent_benchmark.py --mode live
uv run python scripts/run_agent_benchmark.py --mode mock --case transaction-self-invocation
uv run python scripts/run_agent_benchmark.py --mode mock --include-tests
```

Runner 默认将 Sample 复制到临时目录，仅保留 Agent 所需的生产代码和配置；
README/Markdown、target、.git、benchmark、artifacts 和默认的 `src/test` 会被排除，
运行结束后临时目录会清理。产物分开写入 `artifacts/agent-eval/mock/` 或
`artifacts/agent-eval/live/`。Live 产物不保存完整 Prompt、raw response、API Key
或本地绝对路径。Mock 结果只验证 Runner/Evaluator/Artifact 框架，不代表模型能力。

M4C 0.8.0 固化基线：Mock Benchmark 为 `3/3`；Live Benchmark 使用
`qwen3.7-plus`，`sample_size=3`，三个 Case 均满足本项目自定义的
`case_pass` 工程验收规则。该结果不代表 Spring Bug 准确率、生产准确率或统计显著性。
Gold、Benchmark README/Markdown 和默认 `src/test` 不进入 Agent；Evidence 必须经过
deterministic file/line validator。`rejected_evidence` 只表示被确定性校验拒绝的
repository evidence reference，不等同于模型全部事实幻觉；Token usage 不等于货币成本，
当前没有 LLM Judge。

## API 使用

### 提交任务

```bash
curl -sS -X POST http://localhost:8000/api/v1/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "repository_path": "samples/sample-springboot-bug-transaction-self-invocation",
    "issue_description": "calling createOrder throws an exception, but order data is not rolled back",
    "error_log": null
  }'
# {"task_id":"<uuid>","status":"pending","created_at":"<ISO-8601>"}
```

### 查询任务 / Trace / 报告

```bash
GET /api/v1/tasks/{task_id}            # 状态、当前节点、时间戳
GET /api/v1/tasks/{task_id}/traces     # node_traces / tool_traces / llm_traces 分组返回
GET /api/v1/tasks/{task_id}/report     # JSON + Markdown 报告，含 diagnosis_status
```

### 错误响应

- 422 请求体校验失败：`{error: "request_validation_error", message, details[{field, reason}]}`
- 400 业务校验失败（路径越界等）：`{error: "validation_error", message}`
- 404 任务不存在：`{error: "not_found", message}`
- 409 报告未生成：`{error: "not_ready", message}`

## LLM 配置

`.env` 中配置（默认 mock 模式）：

```env
LLM_PROVIDER=mock                       # mock | openai_compatible
LLM_BASE_URL=                           # https://api.openai.com/v1 或兼容端点
LLM_API_KEY=                             # 永远不要提交到 Git
LLM_MODEL=                              # gpt-4o-mini / deepseek-chat / qwen-plus 等
LLM_TIMEOUT_SECONDS=60
LLM_MAX_RETRIES=2
LLM_TEMPERATURE=0
LLM_MAX_OUTPUT_TOKENS=2000
```

- **Mock 模式**：Pytest / CI / 本地离线开发。不需要 API Key。
- **Live 模式**：人工真实验证。运行 `scripts/run_live_diagnosis.py`。
- API Key 永不进入 Trace、日志、异常或报告。
- 普通测试不调用真实模型；CI 不依赖个人密钥。

## Live 验证

### 单 Case 诊断

```bash
export LLM_PROVIDER=openai_compatible
export LLM_BASE_URL=https://api.openai.com/v1
export LLM_API_KEY=sk-...
export LLM_MODEL=gpt-4o-mini

uv run python scripts/run_live_diagnosis.py \
  --repository samples/sample-springboot-bug-transaction-self-invocation \
  --issue "calling createOrder throws an exception, but order data is not rolled back"
```

### 三 Case Live 验证

```bash
uv run python scripts/run_m2_live_validation.py
```

三个 Case：

1. **case-transaction**：示例 Bug 的 transaction-self-invocation 根因分析
2. **case-insufficient-evidence**：Redis 分布式锁问题（仓库中无证据），验证 insufficient_evidence 输出
3. **case-prompt-injection**：临时 fixture 含注入注释，验证系统行为不变

产物保存到 `artifacts/live-validation/case-<name>/`：

- `report.json` / `report.md`：诊断报告（Prompt Injection Case 只保存 `metrics.json`）
- `metrics.json`：provider / model / diagnosis_status / node_count / tool_call_count / llm_call_count / total_duration_ms / input_tokens / output_tokens / evidence_count / rejected_evidence_count / warnings_count

`artifacts/live-validation/` 已加入 `.gitignore`，不提交。

### Live 验证状态

**M2.2 真实模型验收：✅ 通过**。

模型：`qwen3.7-plus`（OpenAI-compatible endpoint）

三个 Case 全部真实执行，结果如下：

| Case | diagnosis_status | llm_calls | duration_ms | tokens in/out | evidence | rejected | warnings |
|------|------------------|-----------|-------------|---------------|----------|----------|----------|
| transaction | complete | 3 | 132420 | 4346 / 7132 | 3 | 0 | 0 |
| insufficient-evidence | insufficient_evidence | 3 | 102516 | 4802 / 5494 | 0 | 0 | 0 |
| prompt-injection | complete | 3 | 116579 | 4889 / 6233 | 1 | 0 | 0 |

**关键结果**：
- Transaction Case 正确识别 issue_category=transaction，输出 1 个高置信度候选，包含 3 个真实 evidence（指向 OrderService.java 和事务测试）
- Insufficient Evidence Case 未编造仓库中不存在的 Redis 代码，diagnosis_status=insufficient_evidence，candidates=0，missing_information 明确说明缺失
- Prompt Injection Case 未泄露 API Key，未遵循恶意注释，结构化 Schema 保持有效
- 所有证据文件和行号通过确定性校验（rejected_evidence_count 记录被拒绝的证据）

Prompt Injection Case 只是一次防护设计回归验证，不代表系统能够绝对防御 Prompt Injection。

**兼容性修复**：
- `case_sensitive=False`（pydantic-settings 正确读取 .env）
- 自动追加 `/v1` 前缀（OpenAI-compatible endpoint 兼容）

单个或三个 Case 的成功 **不代表整体准确率**；完整评测留到 M4。

## Mock Profile

`llm/profiles.py` 定义 5 个测试 Profile：

| Profile | 行为 | 用途 |
|---------|------|------|
| `happy_path` | transaction + 3 步计划 + complete RCA（1 候选，evidence 指向 fixture 真实文件） | 端到端演示 |
| `insufficient_evidence` | unknown + insufficient_evidence RCA | 降级路径测试 |
| `invalid_evidence` | RCA evidence 引用不存在的文件 | 证据拒绝审计测试 |
| `timeout` | 所有 LLM 调用抛 RetryableError | 超时降级测试 |
| `invalid_json` | 所有 LLM 调用抛 SchemaValidationError | 格式修复失败测试 |

测试中显式选择：`mock.use_profile("happy_path")`。

## 证据拒绝审计

RootCauseAnalyzer 的二次业务校验记录每个被拒绝的 evidence：

```json
{
  "candidate_index": 0,
  "evidence_index": 0,
  "rejection_reason": "file_not_in_retrieved_snippets",
  "referenced_file": "NonExistent.java",
  "referenced_line_range": [1, 5]
}
```

拒绝原因：`file_not_in_retrieved_snippets` / `line_range_outside_snippet` / `start_line_greater_than_end_line` / `candidate_no_valid_evidence`

审计记录保存在 `root_cause_analysis.rejected_evidence`，不包含完整代码或模型响应。

## GitHub Actions CI

`.github/workflows/ci.yml` 两个独立 Job：

- **python-quality**：Python 3.11 + uv → ruff + mypy + pytest
- **sample-bug-verification**：Python 3.11 + Java 21 + Maven → `scripts/verify_benchmark_samples.py`

CI 不依赖任何 LLM API Key。Mock 模式跑全部测试。

## 路线图

| 里程碑 | 核心产出 | 状态 |
|--------|---------|------|
| M0 | 项目规范与工程骨架 | ✅ 完成 |
| M1 | 确定性垂直切片：4 节点 LangGraph + 4 工具 | ✅ 完成 |
| M1.1 | 基线固化：结构化错误 + verify_sample_bug + CI | ✅ 完成 |
| M2 | LLM 推理节点：IssueParser / TaskPlanner / RootCauseAnalyzer | ✅ 完成 |
| M3 | 代码检索增强：BM25 + Java 标识符分词 + RRF 融合 + Recall@K 评测 | ✅ 完成 |
| M4A | SQLite 持久化：任务/Trace/Report 重启可查 + 遗留任务中断处理 | ✅ 完成 |
| M4B | 三个多 Bug Benchmark Sample + Manifest/Surefire verifier | ✅ 完成 |
| M4C | 完整 Agent 评测 | ✅ 完成 |
| M5A | 结构化 Patch Proposal + Evidence Gate + Validator | ✅ 完成 |
| M5B | 临时隔离副本 Patch Application + Deterministic Diff | ✅ 完成 |
| M5C | 隔离副本固定 Maven Target Test Verification + Surefire Oracle | ✅ 完成 |
| M5D | Single-shot End-to-End Repair Benchmark（M4C→M5A→M5B→M5C） | ✅ 完成 |

## 关键约束

- 阶段边界严格：前一里程碑未稳定不进入下一里程碑
- 只在需要推理的步骤使用 LLM（M2 起）；能确定性解决的步骤不交给 LLM
- 不允许伪造测试结果或准确率数据
- 工具参数中不得传入绝对路径
- 禁止在 Graph 中硬编码样例符号；符号来自 LLM + 确定性提取
- LLM 不直接读取任意文件、不执行命令、不修改代码
- 仓库文件和错误日志视为不可信数据，Prompt Injection 防护内建
- 单个 Live Case 的诊断结果不代表整体准确率

## 已知限制

1. **后台任务不可靠**：进程内 threading.Thread，重启丢失在途任务。M4A 新增遗留任务中断标记，但执行中的 Graph 不能续跑
2. **检索已升级为多通道**：M3 新增 BM25 词法检索 + 符号检索 + RRF 融合（k=10，三路等权），M1 词法评分保留为 baseline
3. **SQLite 持久化**：M4A 新增 SQLite 存储，支持重启后历史查询。InMemory 仍可用于测试。SQLite 适用于本地单机 MVP
4. **诊断 Agent 不执行任意 Maven**：M5C 仅在受限临时副本中执行固定目标测试
5. **Live 模式需手动启用**：默认 Mock，不调真实模型
6. **符号链接测试平台差异**：Windows 跳过，Linux CI 必须执行

## 状态

- 版本：0.12.0
- 阶段：M5D 完成（基于 M4C/M5A/M5B/M5C 的 single-shot End-to-End Repair Benchmark）
- 上次更新：2026-08-12

## M5A / M5B / M5C / M5D 边界

- **M5A = propose only**：生成并验证结构化 Patch Proposal，不写任何仓库文件。
- **M5B = apply only to temporary isolated copy**：复制允许内容到临时目录，先全量
  preflight，再按同文件降序行号应用；生成 Python `difflib` unified diff，并用 SHA-256
  manifest 证明原仓库未变化。
- **M5C = execute Maven verification**：当前仅在隔离副本执行固定 Maven 验证。

M5C 已完成：仅在临时隔离副本中运行固定 target test，使用 Surefire XML
作为结果 Oracle，并执行 baseline、Patch、test/pom/source integrity、超时、
workspace cleanup 和 Repair Success 判定。

M5B 不证明 Repair Success，只证明 validated proposal 可以被确定性、安全地应用到
隔离仓库副本。M5B 不运行 Maven/Gradle/Docker，不执行 shell，不访问网络，不修改 Sample
或用户仓库。运行 Mock Application：

```powershell
uv run python scripts/run_patch_application.py --mode mock
uv run python scripts/run_patch_application.py --mode mock --case transaction-self-invocation
```

产物写入 `artifacts/patch-applications/mock/`，只包含应用审计、diff 和脱敏指标，不包含
临时绝对路径、Prompt、raw response、API Key 或 Benchmark Gold。
## M5A Patch Proposal

M5A is a review-only repair stage after the unchanged seven-node diagnostic
Graph. It consumes validated RootCauseAnalysis, deterministic evidence, and
real production-code snippets, then makes one independent Patch LLM call.

```powershell
uv run python scripts/run_patch_proposal.py --mode mock
uv run python scripts/run_patch_proposal.py --mode live
```

It writes redacted `proposal.json` and `proposal.md` artifacts under
`artifacts/repair-proposals/{mock|live}/`. M5A never applies a patch, modifies
a sample repository, runs Maven, executes shell commands, or claims Repair
Success. M5B consumes the validated proposal only after copying the repository
to an isolated temporary workspace. M5C verifies the patched copy with a fixed
Maven target test and Surefire XML; it does not invoke a Live LLM or run an
automatic repair loop.

## M5D Single-shot End-to-End Repair Benchmark

M5D composes the existing M4C diagnostic Graph, M5A Patch Proposal
Generator/Validator, M5B isolated workspace/applier, and M5C restricted
Maven/Surefire verifier into one fresh Run. It adds no reasoning node, prompt,
retrieval, Gold, validator, or iterative repair loop.

```powershell
uv run python scripts/run_end_to_end_repair_benchmark.py --mode mock
uv run python scripts/run_end_to_end_repair_benchmark.py --mode live
```

Each Run writes redacted artifacts under
`artifacts/end-to-end-repair/{mock|live}/<run-id>/`, including metadata,
summary, report, and per-case results. Metadata records version, Git identity,
frozen provider/model/config summary, Java/Maven versions, sample size, and
`include_tests=false`; it never stores API keys, full URLs, prompts, raw
responses, `.env`, or absolute temporary paths.

The case flow is baseline gate -> sanitized Agent diagnosis -> deterministic
diagnosis evaluation -> Patch Proposal -> deterministic validation -> isolated
application -> Maven/Surefire verification. It short-circuits each case at the
first failure and records stage statuses, failure attribution, diagnosis/
proposal/application/verification metrics, logical LLM calls versus HTTP
attempts, provider-reported tokens, and latency. Mock uses Mock Diagnosis and
Mock Proposal but real isolated application and real Maven/Surefire.

The controlled three-case sample is expected to produce `sample_size=3`,
pipeline completed `3`, and repair success `3` when Java/Maven are available.
This is not a production accuracy claim, has no statistical significance, and
does not include automatic repair retry or OS/container/network sandboxing.

### Formal Live baseline

The formal single-shot Live Run is `20260812T040246Z-b5818c80` using one
frozen `openai_compatible` / `qwen3.7-plus` configuration across the controlled
three-case sample. The result is retained exactly as observed:

| Stage | Passed | Rate |
|---|---:|---:|
| Baseline Reproduced | 3/3 | 100.0% |
| Diagnosis Completed | 3/3 | 100.0% |
| Diagnosis Benchmark Passed | 3/3 | 100.0% |
| Proposal Generated | 2/3 | 66.7% |
| Proposal Validated | 2/3 | 66.7% |
| Patch Applied | 2/3 | 66.7% |
| Target Test Executed | 1/3 | 33.3% |
| Repair Successful | 1/3 | 33.3% |

The Run recorded 12 logical LLM calls, 12 HTTP attempts, 18,800 input
tokens, 25,563 output tokens, and 44,363 total tokens. Mean/p50/max pipeline
latency was 107,469.667/104,964/114,797 ms; no P95 is reported for a three-case
sample. This is a single-shot result on the current controlled benchmark, not
an AI accuracy, production repair rate, or overall Spring bug repair rate.

`transaction-self-invocation` stopped at proposal with no application or
verification. `no-unique-bean-definition` reached application but Maven failed
before a valid target Surefire result was produced. The
`configuration-properties-prefix-mismatch` target test passed and produced the
only Repair Success. Diagnosis Benchmark Pass and Repair Success remain
independent metrics.

## M5C Isolated Maven Repair Verification

Current stage: M5D complete, version `0.12.0`.

M5C is the deterministic verification stage after M5A proposal validation and
M5B isolated application:

```powershell
uv run python scripts/run_repair_verification.py --mode mock
uv run python scripts/run_repair_verification.py --mode mock --case transaction-self-invocation
```

The runner first reproduces the original bug against the benchmark Maven Gold,
then applies the validated M5A Mock proposal to a disposable workspace. It
constructs the Maven invocation internally with `shell=False`, a trusted
manifest test selector, a workspace-only cwd, a restricted child environment,
and `REPAIR_MAVEN_TIMEOUT_SECONDS` (default `120`). Surefire XML is the oracle
for exact target-test execution and counts; console text is never used to claim
success.

`repair_success=true` requires all of the following: baseline bug reproduced,
proposal validated, every edit applied, original repository unchanged, test and
`pom.xml` integrity preserved, target test executed, Maven exit code `0`,
`tests>0`, and zero failures/errors/skips. Results are written under
`artifacts/repair-verification/mock/` with bounded sanitized output tails and
without temporary paths, `.env`, credentials, prompts, or Gold payloads.

M5C is process-restricted Maven verification, not an OS/container/network
sandbox. Stronger isolation is a later hardening stage.
