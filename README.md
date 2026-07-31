# SpringFix Agent

面向 Java/Spring Boot 项目的智能故障诊断与修复平台。

> 面向 Agent 应用开发岗位面试的个人项目。核心不在产品形态，而在体现 LangGraph 状态编排、Tool Calling、多步骤规划、Java 代码混合检索、Agent 可观测性、Agent 评测、Java/Python 双服务协作等工程能力。

## 当前阶段

**M3（代码检索增强）** 已完成。M2 Agent 工作流基础上新增多通道代码检索模块，提升候选文件召回质量。

M2 产出：

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
uv run python scripts/run_retrieval_eval.py  # M3 检索评测
```

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
- **sample-bug-verification**：Python 3.11 + Java 21 + Maven → `scripts/verify_sample_bug.py`

CI 不依赖任何 LLM API Key。Mock 模式跑全部测试。

## 路线图

| 里程碑 | 核心产出 | 状态 |
|--------|---------|------|
| M0 | 项目规范与工程骨架 | ✅ 完成 |
| M1 | 确定性垂直切片：4 节点 LangGraph + 4 工具 | ✅ 完成 |
| M1.1 | 基线固化：结构化错误 + verify_sample_bug + CI | ✅ 完成 |
| M2 | LLM 推理节点：IssueParser / TaskPlanner / RootCauseAnalyzer | ✅ 完成 |
| M3 | 代码检索增强：BM25 + Java 标识符分词 + RRF 融合 + Recall@K 评测 | ✅ 完成 |
| M4 | 持久化与评测：SQLite + 3 个 Bug + 评测 Runner | 待启动 |

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

1. **后台任务不可靠**：进程内 threading.Thread，重启丢失在途任务
2. **检索已升级为多通道**：M3 新增 BM25 词法检索 + 符号检索 + RRF 融合（k=10，三路等权），M1 词法评分保留为 baseline
3. **InMemory 存储**：重启丢失所有任务和 Trace
4. **Agent 不执行 Maven**：示例 Bug 可 `mvn test` 复现，但 Agent 不执行 Maven
5. **Live 模式需手动启用**：默认 Mock，不调真实模型
6. **符号链接测试平台差异**：Windows 跳过，Linux CI 必须执行

## 状态

- 版本：0.5.0
- 阶段：M3 完成（代码检索增强）
- 上次更新：2026-07-31
