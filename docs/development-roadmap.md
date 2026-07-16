# 开发路线图（Development Roadmap）

## 当前状态

- 阶段：M1（确定性垂直切片）已完成
- 状态：M0 ✅ 完成 / M1 ✅ 完成
- 上次更新：2026-07-16

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

## M2 任务清单（待启动）

| ID | 任务 |
|----|------|
| T2.1 | 定义 `LLMClient` Protocol |
| T2.2 | 实现 `MockLLMClient` |
| T2.3 | 实现 `OpenAICompatibleClient` |
| T2.4 | 实现 `IssueParser` 节点 |
| T2.5 | 实现 `TaskPlanner` 节点 |
| T2.6 | 实现 `RootCauseAnalyzer` 节点 |
| T2.7 | Pydantic 结构化输出 |
| T2.8 | Prompt 模板 |
| T2.9 | LLM 超时、重试、降级 |
| T2.10 | AgentState 扩展 M2 字段 |
| T2.11 | LangGraph 扩展为 6 节点 |
| T2.12 | 真实模型端到端测试 |

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
