# 开发路线图（Development Roadmap）

## 当前状态

- 阶段：M2（LLM 推理节点）已完成
- 状态：M0 ✅ / M1 ✅ / M1.1 ✅ / M2 ✅
- 上次更新：2026-07-29

## M0 任务清单（已完成）

| ID | 任务 | 状态 |
|----|------|------|
| T0.1 | 检查 Python/uv 环境 | 完成 |
| T0.2 | 创建项目文档（8 份） | 完成 |
| T0.3 | 创建工程配置（pyproject、.gitignore、.env.example） | 完成 |
| T0.4 | 创建源码骨架（FastAPI + Protocol + Models） | 完成 |
| T0.5 | 创建启动脚本（Windows + WSL） | 完成 |
| T0.6 | 编写健康检查测试 | 完成 |
| T0.7 | 执行 Ruff 检查 | 完成 |
| T0.8 | 执行 MyPy strict 检查 | 完成 |
| T0.9 | 执行 Pytest | 完成 |
| T0.10 | 启动 FastAPI 验证健康检查 | 完成 |
| T0.11 | 汇总结果并自检 | 完成 |

## M1 任务清单（已完成）

| ID | 任务 | 状态 |
|----|------|------|
| T1.1 | 创建 `graph/state.py` AgentState（M1 版） | 完成 |
| T1.2 | 创建 `graph/builder.py` 4 节点线性图 | 完成 |
| T1.3 | 创建 `tools/_path_safety.py` 路径校验模块 | 完成 |
| T1.4 | 实现 `list_project_tree` 工具 | 完成 |
| T1.5 | 实现 `search_code` 工具（简单词法评分） | 完成 |
| T1.6 | 实现 `read_file` 工具（含沙箱） | 完成 |
| T1.7 | 实现 `find_java_symbol` 工具（正则） | 完成 |
| T1.8 | 实现 `InMemoryTaskRepository` | 完成 |
| T1.9 | 实现 `InMemoryTracer` | 完成 |
| T1.10 | 实现 `TaskService.submit_task` + `run_task_sync` | 完成 |
| T1.11 | 实现 4 个 Graph 节点 | 完成 |
| T1.12 | 实现 `POST /api/v1/tasks` 及查询接口 | 完成 |
| T1.13 | 创建示例 Bug 项目 `transaction-self-invocation` | 完成 |
| T1.14 | 工具单元测试 + 端到端集成测试 | 完成 |
| T1.15 | Ruff + MyPy + Pytest 全部通过 | 完成 |

## M1.1 任务清单（已完成 — 基线固化，不新增 Agent 能力）

| ID | 任务 | 状态 |
|----|------|------|
| T1.1.1 | 统一 RequestValidationError 返回结构化 `{error, message, details[]}` | 完成 |
| T1.1.2 | 创建 `scripts/verify_sample_bug.py` 示例 Bug 跨平台验证脚本 | 完成 |
| T1.1.3 | 创建 `.github/workflows/ci.yml`：`python-quality` + `sample-bug-verification` | 完成 |
| T1.1.4 | 收窄 StarletteDeprecationWarning 过滤到 message 级别 | 完成 |
| T1.1.5 | 为 `graph/builder.py` 4 处 `# type: ignore[call-overload]` 加说明注释 | 完成 |
| T1.1.6 | 文档更新：README / CLAUDE / architecture / development-roadmap | 完成 |
| T1.1.7 | 最终验证：ruff + mypy + pytest + verify_sample_bug.py | 完成 |

## M2 任务清单（已完成 — LLM 推理节点）

| ID | 任务 | 状态 |
|----|------|------|
| T2.1 | 创建 LLM 层：`llm/{client, mock, openai_compatible, schemas, parser, _retry, trace, prompts}` | 完成 |
| T2.2 | 扩展 AgentState：`issue_analysis` / `investigation_plan` / `root_cause_analysis` / `diagnostic_report` / `llm_calls` / `warnings` | 完成 |
| T2.3 | 扩展 Tracer：`record_llm_call`，Trace.kind 支持 `llm_call` | 完成 |
| T2.4 | 扩展 Settings：`LLM_PROVIDER` / `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` 等 | 完成 |
| T2.5 | 实现 `issue_parser` 节点（LLM + 降级） | 完成 |
| T2.6 | 实现 `task_planner` 节点（LLM + 降级） | 完成 |
| T2.7 | 实现 `root_cause_analyzer` 节点（LLM + 二次业务校验） | 完成 |
| T2.8 | 实现 `build_diagnostic_report` 节点（确定性，区分 diagnosis_status） | 完成 |
| T2.9 | 修改 `explore_repository`：合并 LLM + 确定性符号 | 完成 |
| T2.10 | 修改 `retrieve_code`：查询来源扩展（search_terms / target_symbols / exception_types） | 完成 |
| T2.11 | 扩展 `graph/builder.py`：7 节点线性图 | 完成 |
| T2.12 | 扩展 API：traces 响应区分 node / tool / llm | 完成 |
| T2.13 | 修改 `TaskService`：接受 LLMClient | 完成 |
| T2.14 | 修改 `main.py`：根据 LLM_PROVIDER 构造 LLM 客户端 | 完成 |
| T2.15 | 创建 `scripts/run_live_diagnosis.py` | 完成 |
| T2.16 | 更新 `.env.example`：LLM 配置占位 | 完成 |
| T2.17 | 测试：LLM client / parser / schemas / prompts / 3 节点 / e2e / injection | 完成 |
| T2.18 | 最终验证：ruff + mypy + pytest + verify_sample_bug | 完成 |
| T2.19 | 三个真实模型 Live Case 回归（transaction / insufficient-evidence / prompt-injection） | 完成 |

三个 Live Case 只记录一次真实模型回归结果，不代表整体准确率。Prompt Injection
Case 只验证当前防护设计和一次模型行为，不代表绝对安全。

## M3 任务清单（待启动）

| ID | 任务 |
|----|------|
| T3.1 | BM25 实现 |
| T3.2 | Java 标识符分词 |
| T3.3 | `find_java_symbol` 优化 |
| T3.4 | 方法级或代码块级切分 |
| T3.5 | 简单词法 vs BM25 Recall@K 对比 |
| T3.6 | AgentState 扩展 M3 字段 |

## M4 任务清单（待启动）

| ID | 任务 |
|----|------|
| T4.1 | `SqliteTaskRepository` 实现 |
| T4.2 | SQLite Schema 与迁移 |
| T4.3 | 创建 2 个新 Bug 样本（共 3 个） |
| T4.4 | 评测 Runner `scripts/run_eval.py` |
| T4.5 | 评测指标报告输出 |
| T4.6 | README 补充实际评测结果 |

## 阶段切换准则

进入下一里程碑的前提：

1. 当前里程碑所有验收标准通过
2. 没有创建任何下一里程碑的提前实现文件
3. 用户明确确认"进入下一里程碑"

## 后续阶段（阶段 2+）

| 阶段 | 主要内容 |
|------|---------|
| 阶段 2 | Vue 前端、Spring Boot 后端、MySQL/Redis/MinIO、SSE |
| 阶段 3 | Docker 沙箱、Maven 测试、自动代码修改、反思修正、HITL |
| 阶段 4 | MCP、Nginx、Docker Compose 生产部署 |
