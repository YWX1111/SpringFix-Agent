# 评测设计（Evaluation Design）

> 本文档仅定义评测设计。评测运行器 `scripts/run_eval.py` 与实际评测结果输出推迟到 M4。M0-M3 期间不输出任何准确率或命中率数据。

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

## 6. 评测脚本设计（M4 实现）

文件：`scripts/run_eval.py`

接口：

```bash
uv run python scripts/run_eval.py --dataset tests/eval/cases.jsonl --output-dir eval_results/
```

行为：

1. 加载 `cases.jsonl`
2. 对每条用例：
   - 调用 `POST /api/v1/tasks` 提交
   - 轮询 `GET /api/v1/tasks/{id}` 直到 `status` 为 `completed` 或 `failed`
   - 获取 `GET /api/v1/tasks/{id}/traces` 和 `/report`
   - 计算指标
3. 输出汇总报告到 `eval_results/`

## 7. 当前阶段状态

- M0：仅定义评测设计（本文档）
- M1：无评测输出
- M2：无评测输出
- M2 的三个 Live Case 仅用于真实模型回归，不作为准确率或命中率评测
- M3：仅做检索指标对比（简单词法 vs BM25 Recall@K），不输出根因命中率
- M4：完整评测运行与指标输出

**M0-M3 期间禁止输出任何准确率或命中率数据**。
