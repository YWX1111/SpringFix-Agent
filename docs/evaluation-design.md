# 评测设计（Evaluation Design）

## M4B Benchmark 边界

M4B 只验证三个故意失败的 Spring Boot Sample、Manifest 金标准和
Surefire 结果，不运行完整 Agent，也不调用真实 LLM，不计算 Agent 或根因准确率。

Agent-facing 输入仅允许 `repository`、`issue_description` 和 `error_log`。
`expected_root_cause_keywords`、`expected_files`、`expected_symbols`、
`evidence_targets` 和 `expected_maven` 只供离线校验使用。

Sample README 与 `benchmark/agent_cases.jsonl` 是 Benchmark 文档/金标准，
M4C Runner 已从 Agent repository copy 中排除它们，避免根因泄漏。

> 本文档定义评测设计。M4C 实现为 `scripts/run_agent_benchmark.py`。M4A 已完成 SQLite 持久化，但 M4C 结果使用脱敏文件 Artifact，不扩展 SQLite schema。M3 检索评测（Recall@K / MRR / P95）是检索质量指标，不等于 Agent 准确率。

## 1. 设计原则

- 评测指标必须可量化、可复现
- 禁止伪造准确率或命中率数据
- 每条评测结果必须关联 `task_id` 可追溯
- 评测脚本每次跑都重新执行 LangGraph，禁止读取缓存结果
- 3 个样本下的指标不具有统计意义，明确标注"3 样本"，不夸大

## 2. 评测数据集 Schema

数据集文件：`tests/eval/cases.jsonl`（M4 创建）

每行一条用例：

```json
{
  "case_id": "bug-001-transaction-self-invocation",
  "repository_path": "samples/sample-springboot-bug-transaction-self-invocation",
  "issue_description": "用户调用 service 的 saveOrder 方法,数据没入库,但没异常",
  "error_log": "可选,可为 null",
  "expected": {
    "issue_category": "transaction",
    "key_files": [
      "src/main/java/com/example/service/OrderService.java"
    ],
    "root_cause_keywords": [
      "@Transactional",
      "self-invocation",
      "self-invoked",
      "AOP proxy",
      "internal call"
    ]
  }
}
```

预期结果文件：`tests/eval/expected_results.json`（M4 创建）

## 3. 评测指标定义

### 3.1 `issue_category_accuracy`

定义：Agent 输出的 `issue_analysis.issue_category` 与 `expected.issue_category` 是否一致。

取值：二值（0 或 1）。

聚合：`sum / N`，N 为评测用例总数。

### 3.2 `key_file_recall@5`

定义：`expected.key_files` 中有多少文件出现在 `retrieved_snippets` 的 top-5。

公式：`|retrieved_top5 ∩ expected.key_files| / |expected.key_files|`

取值：0.0 到 1.0。

聚合：所有用例的平均值。

### 3.3 `root_cause_hit@1`

定义：`root_causes` 第 1 个是否包含 `expected.root_cause_keywords` 中至少 2 个关键词。

取值：二值（0 或 1）。

聚合：`sum / N`。

### 3.4 `root_cause_hit@3`

定义：`root_causes` 前 3 个中是否有任意一个包含 `expected.root_cause_keywords` 中至少 2 个关键词。

取值：二值（0 或 1）。

聚合：`sum / N`。

### 3.5 `average_duration_ms`

定义：单个任务从 `POST /tasks` 到 `status=completed` 的端到端耗时（毫秒）。

聚合：所有用例的算术平均。

### 3.6 `tool_call_count`

定义：单个任务中工具调用次数（`tool_calls` 长度）。

聚合：所有用例的算术平均。

### 3.7 `llm_call_count`

定义：单个任务中 LLM 调用次数。

预期值：M2 起固定为 3（IssueParser + TaskPlanner + RootCauseAnalyzer）。

聚合：所有用例的算术平均。

## 4. 评测输出格式（M4 实现）

```
case_id                                    | issue_category_acc | key_file_recall@5 | root_cause_hit@1 | root_cause_hit@3 | duration_ms | tool_calls | llm_calls
bug-001-transaction-self-invocation        | ✓               | 1.00               | ✓                | ✓                | 8234        | 7          | 3
bug-002-di-missing-bean                    | ✓               | 0.50               | ✗                | ✓                | 9102        | 5          | 3
bug-003-config-yaml-indent                | ✗               | 1.00               | ✗                | ✗                | 7521        | 6          | 3
─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Summary                                    | 2/3 (66.7%)     | avg 0.83           | 1/3 (33.3%)      | 2/3 (66.7%)      | avg 8286ms  | avg 6.0    | avg 3.0
```

输出文件：

- `eval_results.json`：结构化结果
- `eval_results.md`：人类可读 Markdown 报告

## 5. 评测用例设计要求

M4 评测数据集至少包含 3 个可复现 Spring Boot Bug：

| Case ID | issue_category | Bug 描述 |
|---------|-------------|---------|
| bug-001-transaction-self-invocation | transaction | 同类内部方法调用导致 `@Transactional` 代理失效 |
| bug-002-? | 待定 | 待定 |
| bug-003-? | 待定 | 待定 |

每个 Bug 必须满足：

- 可独立 `mvn test` 复现
- sample README 记录 Bug 描述、预期行为、实际行为、根因、复现命令、预期失败测试名称
- 不使用伪造的复现结果

## 6. M4C 评测脚本

文件：`scripts/run_agent_benchmark.py`

接口：

```bash
uv run python scripts/run_agent_benchmark.py --mode mock
uv run python scripts/run_agent_benchmark.py --mode live
```

行为：

1. 加载 `benchmark/agent_cases.jsonl`。
2. 对每条用例创建 sanitized repository copy，执行完整 7 节点 Graph。
3. 删除临时副本后，由 deterministic evaluator 使用 Gold 比较 Agent 输出。
4. 输出到 `artifacts/agent-eval/mock/` 或 `artifacts/agent-eval/live/`。

### 6.1 M4C 0.8.0 固化基线

- Mock Benchmark：`sample_size=3`，`3/3`，只验证 Runner/Evaluator/Artifact 链路，不代表模型能力。
- Live Benchmark：使用 `qwen3.7-plus`，3 个 Case 均满足项目自定义 `case_pass` 工程规则。
- Agent-facing 输入只有 `repository`、`issue_description`、`error_log`；Gold、Benchmark README/Markdown 和默认 `src/test` 不进入 Agent。
- Evidence 必须通过 deterministic file/line validator；`rejected_evidence` 只衡量无效 repository evidence reference，不等同于模型全部事实幻觉。
- Live Artifact 只保留脱敏结构化结果；不保存 API Key、Authorization/Bearer、完整 Base URL、完整 Prompt、raw response 或本机路径。
- 该基线不代表生产准确率、Spring Bug 总体准确率或统计显著性；Token usage 不等于货币成本，当前没有 LLM Judge。

## 7. 当前阶段状态

- M0：仅定义评测设计（本文档）
- M1：无评测输出
- M2：无评测输出
- M2 的三个 Live Case 仅用于真实模型回归，不作为准确率或命中率评测
- M3：检索评测（Recall@1/3/5、MRR@10、P95 query time），不输出 Agent 根因命中率
- M4C：完整评测运行与指标输出（已完成）

**M0-M3 期间禁止输出 Agent 准确率或命中率数据**。M3 检索评测指标是检索质量度量，不等于 Agent 准确率。

## 8. M3 检索评测（已完成）

M3 新增独立的检索质量评测，与 Agent 评测分离。

### 评测数据集

文件：`tests/fixtures/retrieval/benchmark/retrieval_cases.jsonl`（13 个 case，7 Development + 6 Holdout）

### 评测指标

| 指标 | 定义 |
|------|------|
| Recall@1 | top-1 检索结果中包含相关文件的比率 |
| Recall@3 | top-3 检索结果中包含相关文件的比率 |
| Recall@5 | top-5 检索结果中包含相关文件的比率 |
| MRR@10 | Mean Reciprocal Rank（前 10 个结果中第一个相关结果的倒数排名的均值） |
| P95 query time | 95 分位查询延迟 |

### 运行方法

```bash
uv run python scripts/run_retrieval_eval.py
```

### 重要说明

- 检索评测指标（Recall@K / MRR / P95）衡量的是**检索模块质量**，不是 Agent 整体准确率
- Agent 准确率评测（issue_category_accuracy / root_cause_hit@K 等）推迟到 M4
- Baseline（M1 词法评分）可用于对照，但两者都是词法检索，不是语义对比
- Symbol 通道的部分输入来自模拟的 `IssueAnalysis.extracted_symbols`，属于 enriched-query retrieval
- `expected_symbols` 只作为金标，不进入 `RetrievalQuery`
- 当前评测主要是相关文件级 Recall/MRR；方法块、行号和证据片段级排序质量尚未被完整量化
- 后续完整评测可增加 Evidence Hit@K、Relevant Line Range Recall@K 和 First Relevant Chunk Rank
- Hybrid 的定位是提高 Top-K 召回完整性，不代表全面提升 Top-1 排序
- Development 用于有限参数选择，Holdout 只用于冻结后的验证
- `k=10`、三路等权是在当前指标全部相同情况下选择的简单配置，不是大规模调优结果
- BM25 是词法检索，不是语义检索
- 当前 Benchmark 样本规模小（13 case），不代表生产环境召回率或 Agent 根因准确率
## M5A Repair Proposal metrics

M5A is evaluated separately from the M4C diagnostic benchmark. Each case
records proposal status, edit counts, validated and rejected edits, valid edit
rate, allowed-file rate, evidence-supported edit rate, real `old_code` match
rate, acceptable-change concept hit, forbidden-file edits, diagnostic versus
patch LLM calls, HTTP attempts, token usage, and latency.

Aggregate output uses `sample_size`, `proposal_generation_rate`,
`proposal_validation_rate`, `mean_valid_edit_rate`,
`evidence_supported_edit_rate`, `acceptable_change_concept_hit_rate`, and
`unsafe_proposal_rate`. These are proposal-stage metrics only and do not claim
Repair Success. Gold is loaded only by the deterministic evaluator and never
enters the Patch Prompt.
