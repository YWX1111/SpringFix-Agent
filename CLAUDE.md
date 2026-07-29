# 项目级开发约束（SpringFix Agent）

> 本文件仅约束 SpringFix Agent 项目内的开发，不覆盖工作站上的全局配置。

## 阶段定位

当前阶段：**M2 LLM 推理节点（已完成）**。

M2 在 M1 确定性工作流基础上新增 3 个 LLM 节点，受控升级为完整 Agent 工作流。**不新增 BM25 / SQLite / Docker 等能力**。

M2 范围内已完成：

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
- 示例 Bug 验证脚本：`scripts/verify_sample_bug.py`
- GitHub Actions：`.github/workflows/ci.yml`（python-quality + sample-bug-verification）
- Warning 过滤收窄：StarletteDeprecationWarning 用 message 限定
- LangGraph type ignore：7 处 `# type: ignore[call-overload]` 保留并加说明
- 符号链接测试说明：Windows 本地跳过；Linux CI 必须执行

## M2 明确禁止创建

- BM25 实现 → 推迟到 M3；Embedding / FAISS / Tree-sitter 留到后续里程碑
- SQLite 实现 → 推迟到 M4
- Vue 前端 / Spring Boot 后端 / MySQL / Redis / MinIO → 推迟到阶段 2+
- Docker 沙箱 / Maven 测试执行 / 自动代码修改 → 推迟到阶段 3+
- 评测运行器 → 推迟到 M4
- 多 Agent / 循环 / Reflection → 推迟到阶段 3+
- 任何 `raise NotImplementedError` 的占位实现文件
- 任何 M3 字段占位（检索评分 / 代码块 / 检索元数据）

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
- M3：加入检索评分、代码块、检索元数据

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

## 检索评分规则（M1 起强制）

M1 `search_code` 实现简单确定性词法评分：

- 普通关键词命中：加基础分
- 类名、方法名命中（lowerCamelCase / UpperCamelCase）：提高权重
- 异常类名命中（...Exception）：提高权重
- Spring 注解命中（@...）：提高权重
- 按总分降序返回 Top K
- 无任何命中时返回空结果
- M1 不引入 `rank_bm25`，M3 再实现并通过同一批 Case 对比 Recall@K

## 评测指标（M4 落地，M1 仅落盘设计）

保留 7 个指标定义：

- `issue_category_accuracy`
- `key_file_recall@5`
- `root_cause_hit@1`
- `root_cause_hit@3`
- `average_duration_ms`
- `tool_call_count`
- `llm_call_count`

M1-M3 期间不输出任何准确率或命中率。评测脚本 `scripts/run_eval.py` 推迟到 M4。

## Git 策略

- M0/M1/M1.1/M2 不执行 Git commit（用户明确要求）
- 后续 Git commit 策略由用户指定

## 阶段切换准则

进入下一里程碑的前提：

1. 当前里程碑所有验收标准通过（ruff + mypy strict + pytest + 实际启动验证 + 示例 Bug Maven 预期失败验证 + verify_sample_bug.py 通过）
2. 没有创建任何下一里程碑的提前实现文件
3. 用户明确确认"进入下一里程碑"
