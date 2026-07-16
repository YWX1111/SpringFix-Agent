# 项目级开发约束（SpringFix Agent）

> 本文件仅约束 SpringFix Agent 项目内的开发。不覆盖全局 `C:\Users\Administrator\.claude\CLAUDE.md`。

## 阶段定位

当前阶段：**M1 确定性垂直切片（已完成）**。

M1 范围内已完成：

- 文档：README、本文件、product-requirements、architecture、mvp-scope、development-roadmap、evaluation-design、decisions/0001-mvp-first
- 工程骨架：pyproject.toml、.gitignore、.env.example
- API 层：`/api/v1/health`、`/api/v1/tasks`（POST/GET）、`/tasks/{id}/traces`、`/tasks/{id}/report`
- 工具层（`tools/`）：
  - `base.py`（Tool Protocol + ToolContext + ToolResult）
  - `_path_safety.py`（canonicalize_repository / resolve_relative_path / is_within）
  - `_java_patterns.py`（Java 正则，集中维护，M3 可替换为 Tree-sitter）
  - `_invoker.py`（invoke_tool 包装 Tool.run，自动计时与 Tracer 记录）
  - `list_project_tree.py`、`search_code.py`（简单词法评分，非 BM25）、`read_file.py`（含沙箱与 60 行/4000 字符截断）、`find_java_symbol.py`（正则）
- 存储层（`storage/`）：
  - `models.py`（Task / Trace / Report + TaskStatus）
  - `repository.py`（TaskRepository Protocol）
  - `in_memory.py`（InMemoryTaskRepository，进程内 dict + RLock）
- 可观测层（`observability/`）：
  - `tracer.py`（Tracer Protocol + NodeTiming）
  - `in_memory_tracer.py`（InMemoryTracer，写入 TaskRepository）
- LangGraph 层（`graph/`）：
  - `state.py`（AgentState TypedDict，仅 M1 字段，无 M2 占位）
  - `builder.py`（4 节点静态线性图）
  - `nodes/__init__.py`、`validate_input.py`、`explore_repository.py`、`retrieve_code.py`、`build_basic_report.py`、`_symbol_extraction.py`
- 服务层（`service/`）：`task_service.py`（TaskService.submit_task + run_task_sync）
- 示例 Bug 项目：`samples/sample-springboot-bug-transaction-self-invocation`（`@Transactional` 同类内部调用绕过 AOP 代理）
- 测试：55 通过 + 1 跳过（Windows 符号链接权限）

## M1 明确禁止创建

- `llm/` 任何文件（含 LLMClient Protocol、MockLLMClient）→ 推迟到 M2
- Prompt 模板 → 推迟到 M2
- BM25 / FAISS / Tree-sitter 实现 → 推迟到 M3
- SQLite 实现 → 推迟到 M4
- Vue 前端 / Spring Boot 后端 / MySQL / Redis / MinIO → 推迟到阶段 2+
- Docker 沙箱 / Maven 测试执行 / 自动代码修改 → 推迟到阶段 3+
- 评测运行器 → 推迟到 M4
- 任何 `raise NotImplementedError` 的占位实现文件
- 任何 M2 字段占位（issue_class / plan_steps / root_causes）

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
- M2：加入 `issue_class`、`investigation_plan`、`root_causes` 等字段
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

- `issue_class_accuracy`
- `key_file_recall@5`
- `root_cause_hit@1`
- `root_cause_hit@3`
- `average_duration_ms`
- `tool_call_count`
- `llm_call_count`

M1-M3 期间不输出任何准确率或命中率。评测脚本 `scripts/run_eval.py` 推迟到 M4。

## Git 策略

- M0/M1 不执行 Git commit（用户明确要求）
- 后续 Git commit 策略由用户指定

## 阶段切换准则

进入下一里程碑的前提：

1. 当前里程碑所有验收标准通过（ruff + mypy strict + pytest + 实际启动验证 + 示例 Bug Maven 预期失败验证）
2. 没有创建任何下一里程碑的提前实现文件
3. 用户明确确认"进入下一里程碑"
