# ADR 0001：MVP 优先，按里程碑演进

**Date**: 2026-07-15
**Status**: Accepted

## Context

SpringFix Agent 是面向 Agent 应用开发岗位面试的个人项目，最终技术栈涵盖 Vue 前端、Spring Boot 后端、Python Agent 服务、MySQL/Redis/MinIO 存储层、Docker 沙箱等。若一次性开发完整前后端与所有能力，存在以下风险：

1. **范围失控**：项目过大，无法在合理时间内完成可验证的产出
2. **Agent 核心链路未验证先做外围**：前端、用户系统、存储等并非 Agent 项目核心，先做会偏离面试展示意图
3. **LLM 调用成本与延迟**：所有节点都走 LLM 会让单个任务耗时与成本不可控
4. **示例 Bug 单一无法体现泛化**：单一示例 Bug 无法体现项目泛化能力，但多个 Bug 又超出第一阶段范围
5. **评测可信度**：3 个样本下"准确率"无统计意义，但写"100% 准确率"会被拆穿
6. **路径安全**：本地路径输入若无沙箱会变成任意文件读取漏洞
7. **BM25 对 Java 代码的召回上限**：BM25 对自然语言 OK，对 Java 这种结构化语言会漏掉语义相关但关键词不同的文件

## Decision

采用按里程碑演进策略，每个里程碑必须能独立运行和验证，前一里程碑未稳定不进入下一里程碑。

### 里程碑划分

- **M0**：项目规范与工程骨架。只做文档、Python 工程骨架、长期稳定 Protocol、FastAPI 健康检查。不实现任何 Agent 业务逻辑。
- **M1**：确定性垂直切片。4 节点线性 LangGraph + 4 工具最简实现 + InMemory 存储 + 1 个 Bug 样本。不调用真实 LLM。
- **M2**：LLM 推理节点。IssueParser / TaskPlanner / RootCauseAnalyzer + 真实模型接入 + Pydantic 结构化输出。
- **M3**：代码检索增强。BM25 + Java 标识符分词 + 块级切分 + Recall@K 对比。
- **M4**：持久化与评测。SQLite + 3 个 Bug + 评测 Runner + 实际指标。

### Q1-Q7 决策

**Q1（LLM 提供商）**：采用统一 `LLMClient` 接口。M1 不接入任何模型；M2 起接入 OpenAI-compatible 模型；M2 之前只用 `MockLLMClient` 返回固定 JSON。

**Q2（示例 Bug 数量）**：M1 只创建 1 个示例项目 `transaction-self-invocation`（同类内部方法调用导致 `@Transactional` 代理失效）。M4 评测阶段再补 2 个共 3 个。明确不使用 `@Transactional` 标在 private 方法作为示例 Bug。

**Q3（评测指标）**：保留 7 个指标设计（issue_category_accuracy、key_file_recall@5、root_cause_hit@1、root_cause_hit@3、average_duration_ms、tool_call_count、llm_call_count）。M0 仅落盘设计文档，M4 才实现评测运行器与输出。M0-M3 期间不输出任何准确率或命中率数据。

**Q4（路径沙箱）**：采用 `allow_root` 方案。所有项目路径必须位于 `allow_root` 子目录中。工具只接收相对 `repository_path` 的路径。即使内部支持绝对路径解析，也必须在 canonicalize 后验证路径仍位于 `repository_path` 内。禁止工具读取仓库外文件。

**Q5（存储方案）**：M1 第一垂直切片实现 `InMemoryTaskRepository` 接口，定义 `TaskRepository` Protocol 为后续 SQLite 实现预留接口。M4 才实现 SQLite Schema、迁移和并发写入。

**Q6（状态查询）**：采用 polling：`POST /api/v1/tasks`、`GET /api/v1/tasks/{task_id}`、`GET /api/v1/tasks/{task_id}/traces`、`GET /api/v1/tasks/{task_id}/report`。统一资源化 tasks API。不使用 `POST /api/v1/diagnose`。不实现 SSE 和 WebSocket。

**Q7（LangGraph）**：采用静态线性图。M1 为 4 节点线性图（validate_input → explore_repository → retrieve_code → build_basic_report）。M2 扩展为 7 节点（增加 IssueParser / TaskPlanner / RootCauseAnalyzer，并将末节点替换为 build_diagnostic_report）。不实现条件边、循环、反思、回退。

### 设计矛盾修正

**AgentState 中的代码内容**：State 保存受限代码片段，每片段最多 60 行、最多 4000 字符、最多 10 个片段。禁止保存完整文件。Tool Trace 只保存结果摘要（≤500 字符）。AgentState 总文本长度上限 100KB（初始值，后续根据真实运行数据调整）。

**BM25 定位**：BM25 是词法相关性检索（不是语义检索）。`find_java_symbol` 是精确符号检索。Embedding 是后续的语义检索。三者后续组成混合检索。

**异步任务**：M1 允许使用 FastAPI 进程内异步任务，但必须明确：服务重启会丢失运行中的任务；不支持多实例分布式调度；只是 MVP 临时实现；后续由 Redis Stream 或任务队列替换。集成测试可直接同步调用 `TaskService.run_task_sync`，不通过后台任务等待。

### 进一步缩小 M0

M0 不创建：

- `AgentState`（推迟到 M1）
- `graph/builder.py`（推迟到 M1）
- `graph/nodes`（推迟到 M1）
- `InMemoryTaskRepository` 实现（推迟到 M1）
- `LLMClient` Protocol（推迟到 M2）
- `MockLLMClient`（推迟到 M2）
- `LLM_MOCK` 配置（推迟到 M2）
- M2 字段占位（不提前写入 M0 模型）
- 任何只有 `NotImplementedError`、但当前没有任何调用方的实现文件

M0 保留长期接口：

- `Tool` Protocol
- `TaskRepository` Protocol
- `Tracer` Protocol
- `Task`、`Trace`、`Report` 基础领域模型
- `ErrorResponse`、`HealthResponse`
- `Settings`
- FastAPI App

### M1 工具调用修正

禁止在 Graph 中硬编码 `symbol_name="saveOrder"`。M1 使用以下确定性规则：

1. 优先从 `error_log` 的 Java 堆栈中提取类名和方法名
2. 从 `issue_description` 中提取符合 Java 标识符特征的词
3. 只有提取到明确符号时才调用 `find_java_symbol`
4. 没有明确符号时跳过该工具
5. `find_java_symbol` 本身仍需要独立单元测试

Graph 必须适用于不同仓库和不同方法名。

### M1 search_code 修正

M1 不使用"多关键词全部 AND 命中"。实现简单确定性词法评分：

- 普通关键词命中：加基础分
- 类名、方法名命中：提高权重
- 异常类名命中：提高权重
- Spring 注解命中：提高权重
- 按总分降序返回 Top K
- 没有任何命中时返回空结果，不伪造候选文件

M1 不引入 `rank_bm25`。M3 再实现 BM25，并通过同一批 Case 对比简单词法评分和 BM25 的 Recall@K。

### 示例事务 Bug 复现方式

M1 示例项目使用 Spring Boot + Spring Data JPA 或 JdbcTemplate + H2 内存数据库 + JUnit 5 + Spring Boot Test。Bug 为同类内部调用绕过 Spring AOP 代理导致 `@Transactional` 不生效。示例项目必须包含一个可独立运行的失败测试 `mvn test`，测试通过数据库记录数量证明数据未按预期回滚。Agent 不执行 Maven，该测试只是用于人工验证样例 Bug 真实存在。自动执行 Maven 留到 Docker 沙箱阶段。

## Consequences

- 每个里程碑独立可验证，降低单次失败的影响范围
- M1 先验证确定性链路，LLM 接入推迟到 M2，降低开发期对真实模型的依赖
- M0 不创建空占位文件，避免维护负担
- 评测指标在 M4 才落地，M0-M3 期间不输出任何准确率数据
- 后续阶段（阶段 2+）引入 Vue 前端、Spring Boot 后端等时，Agent 服务的接口边界已稳定，只需对接不需重构

## Compliance

- M0 完成时必须通过 `uv run ruff check`、`uv run mypy --strict`、`uv run pytest` 三项检查
- M0 完成时必须实际启动 uvicorn 并通过 `GET /api/v1/health` 验证
- M0 完成时必须确认未创建任何 M1/M2 提前实现文件
- M0 不执行 Git commit
