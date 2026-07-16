# SpringFix Agent

面向 Java/Spring Boot 项目的智能故障诊断与修复平台。

> 面向 Agent 应用开发岗位面试的个人项目。核心不在产品形态，而在体现 LangGraph 状态编排、Tool Calling、多步骤规划、Java 代码混合检索、Agent 可观测性、Agent 评测、Java/Python 双服务协作等工程能力。

## 当前阶段

**M1（确定性垂直切片）** 已完成。

M1 产出：

- `POST /api/v1/tasks` 提交诊断任务
- `GET /api/v1/tasks/{task_id}` 查任务状态
- `GET /api/v1/tasks/{task_id}/traces` 查工具调用和节点耗时
- `GET /api/v1/tasks/{task_id}/report` 查基础报告
- 4 节点静态线性 LangGraph：
  - `validate_input` → `explore_repository` → `retrieve_code` → `build_basic_report`
- 4 个 Java 代码理解工具：
  - `list_project_tree`：确定性文件树生成
  - `search_code`：简单词法相关性评分（非语义、非 BM25）
  - `read_file`：受限片段读取（≤60 行 / ≤4000 字符）
  - `find_java_symbol`：正则符号匹配（class/interface/enum/record/method/annotation）
- 路径沙箱：`ALLOW_ROOT` 子树限制 + `canonicalize` 后校验
- `InMemoryTaskRepository` + `InMemoryTracer`
- `TaskService.submit_task`（进程内后台线程调度）+ `TaskService.run_task_sync`（同步执行，用于测试）
- 1 个示例 Spring Boot Bug 项目：`samples/sample-springboot-bug-transaction-self-invocation`（`@Transactional` 同类内部调用绕过 AOP 代理）
- 55 个通过测试 + 1 个 Windows 环境下跳过的符号链接测试

M1 **不包含**：

- 任何 LLM 调用（M2 接入）
- BM25 检索（M3 接入）
- SQLite 持久化（M4 接入）
- 根因推理（M2 由 LLM 完成）
- Vue 前端、Spring Boot 业务后端、MySQL/Redis/MinIO
- Docker 沙箱、Maven 测试执行、自动代码修改

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

启动后访问：

- 健康检查：`GET http://localhost:8000/api/v1/health`
- OpenAPI 文档：`GET http://localhost:8000/docs`

## 验证命令

```powershell
uv run ruff check src/ tests/
uv run mypy --strict src/
uv run pytest tests/ -v
```

## API 使用示例

### 提交任务

```bash
curl -sS -X POST http://localhost:8000/api/v1/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "repository_path": "samples/sample-springboot-bug-transaction-self-invocation",
    "issue_description": "calling createOrder throws an exception, but order data is not rolled back",
    "error_log": null
  }'
# 响应:
# {"task_id":"<uuid>","status":"pending","created_at":"<ISO-8601>"}
```

### 查询任务状态

```bash
curl -sS http://localhost:8000/api/v1/tasks/<task_id>
# {"task_id":"...","status":"completed","current_node":"build_basic_report","created_at":"...","started_at":"...","finished_at":"...","error_message":null}
```

### 查询 Trace

```bash
curl -sS http://localhost:8000/api/v1/tasks/<task_id>/traces
# {"task_id":"...","traces":[
#   {"kind":"node_timing","recorded_at":"...","payload":{"node":"validate_input","start":"...","end":"...","duration_ms":2}},
#   {"kind":"tool_call","recorded_at":"...","payload":{"node":"explore_repository","tool_name":"list_project_tree","params":{...},"duration_ms":14,"status":"success","result_summary":"...","error":null}},
#   ...
# ]}
```

### 查询报告

```bash
curl -sS http://localhost:8000/api/v1/tasks/<task_id>/report
# {"task_id":"...","json_report":{...},"markdown_report":"# 诊断报告\n\n> 当前报告由确定性代码检索流程生成...\n\n...","created_at":"..."}
```

## M1 真实执行结果

### 真实 API 调用

```
POST /api/v1/tasks (201):
  task_id: 8ea517e6-ee9a-400b-9e82-45845c49f0d8
  status: pending

GET /api/v1/tasks/8ea517e6-... (200):
  status: completed
  current_node: build_basic_report
  created_at: 2026-07-16T01:21:03.079809Z
  started_at: 2026-07-16T01:21:03.080367Z
  finished_at: 2026-07-16T01:21:03.161132Z
  (总耗时约 82ms)

GET /api/v1/tasks/8ea517e6-.../traces (200):
  trace_count: 10 (4 node_timing + 6 tool_call)
  节点顺序: validate_input -> explore_repository -> retrieve_code -> build_basic_report
  工具调用:
    - list_project_tree (explore_repository): 14ms
    - find_java_symbol "createOrder" (explore_repository): 10ms
    - search_code (retrieve_code): 13ms
    - read_file OrderService.java: 3ms
    - read_file TransactionSelfInvocationTest.java: 3ms
    - read_file Application.java: 2ms

GET /api/v1/tasks/8ea517e6-.../report (200):
  markdown_report length: 4952 chars
  json_report keys: task_id, status, issue_description, extracted_symbols,
                    candidate_files, retrieved_snippets, tool_calls_summary, disclaimer
```

### 真实测试结果

```
uv run ruff check src/ tests/ → All checks passed!
uv run mypy --strict src/     → Success: no issues found in 33 source files
uv run pytest tests/ -v       → 55 passed, 1 skipped in 0.89s
```

### 真实示例 Bug 复现

```
cd samples/sample-springboot-bug-transaction-self-invocation
mvn test

[INFO] Tests run: 1, Failures: 1, Errors: 0, Skipped: 0
[ERROR] TransactionSelfInvocationTest.shouldRollbackOrderWhenInnerMethodThrows:42
  Expected rollback but data was persisted;
  self-invocation bypassed the @Transactional AOP proxy
  ==> expected: <0> but was: <1>
```

失败来源正是目标事务断言，不是编译或配置错误。这正是预期内的 Gold-Standard 失败。

## 路线图

| 里程碑 | 核心产出 | 状态 |
|--------|---------|------|
| M0 | 项目规范与工程骨架 | ✅ 完成 |
| M1 | 确定性垂直切片：4 节点 LangGraph + 4 工具最简实现 + InMemory 存储 + 1 个 Bug 样本 | ✅ 完成 |
| M2 | LLM 推理节点：IssueParser / TaskPlanner / RootCauseAnalyzer + 真实模型接入 | 待启动 |
| M3 | 代码检索增强：BM25 + Java 标识符分词 + 块级切分 + Recall@K 对比 | 待启动 |
| M4 | 持久化与评测：SQLite + 3 个可复现 Bug + 评测 Runner + 实际指标 | 待启动 |

详见 `docs/development-roadmap.md`。

## 关键约束

- 阶段边界严格：前一里程碑未稳定不进入下一里程碑
- 每个阶段必须能独立运行和验证
- 只在需要推理的步骤使用 LLM（M2 起）
- 不允许伪造测试结果或准确率数据
- 工具参数中不得传入绝对路径，路径校验统一在 `tools/_path_safety.py`
- 禁止在 Graph 中硬编码样例符号；`find_java_symbol` 从 `error_log`/`issue_description` 提取

## 已知限制

1. **后台任务不可靠**：M1 使用 `threading.Thread` 在进程内调度任务执行。服务重启会丢失运行中的任务；不支持多个服务实例协调。后续由 Redis Stream 或任务队列替换。
2. **报告不是根因诊断**：M1 报告由确定性代码检索流程生成，明确标注"不代表已经完成根因诊断"。根因分析在 M2 接入 LLM 后实现。
3. **检索为词法相关性**：M1 `search_code` 实现简单词法评分，不引入 BM25、向量检索或语义理解。M3 接入 BM25 并与 M1 简单词法对比 Recall@K。
4. **Agent 不执行 Maven**：示例 Bug 项目必须能 `mvn test` 复现失败，但 Agent 在 M1 阶段不执行 Maven，也不启动 Docker 沙箱。自动执行 Maven 留到 Docker 沙箱阶段。
5. **Windows 符号链接测试跳过**：`test_resolve_relative_path_rejects_symlink_escape` 在无管理员权限的 Windows 环境跳过，非功能缺失。

## 技术栈（最终目标）

详见 `docs/architecture.md`。M1 阶段使用：FastAPI、Uvicorn、Pydantic、Pydantic-Settings、HTTPX、Pytest、Ruff、MyPy、LangGraph。

## 状态

- 版本：0.2.0
- 阶段：M1 完成
- 上次更新：2026-07-16
