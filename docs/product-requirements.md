# 产品需求（Product Requirements）

## 1. 项目定位

SpringFix Agent 是面向 Java/Spring Boot 项目的智能故障诊断与修复平台。

**不是面向最终用户的产品**，而是面向 Agent 应用开发岗位面试的个人项目。其价值在于体现工程能力，而非商业产品形态。

## 2. 最终能力清单（各阶段逐步实现）

| 能力 | 里程碑 |
|------|--------|
| 接收本地 Spring Boot 项目路径 + Issue 描述 + 可选错误日志 | M1 |
| LangGraph 状态编排：节点线性流转 | M1 |
| Tool Calling：4 个 Java 代码理解工具 | M1 |
| Tool Trace 与节点耗时记录 | M1 |
| 基础诊断报告（不含 LLM 推理） | M1 |
| IssueParser：LLM 问题分类 | M2 |
| TaskPlanner：LLM 排查计划 | M2 |
| RootCauseAnalyzer：LLM 根因推理 | M2 |
| Pydantic 结构化 LLM 输出 | M2 |
| 真实模型接入（OpenAI 兼容） | M2 |
| LLM 超时、重试、降级 | M2 |
| BM25 词法相关性检索 | M3 |
| Java 标识符分词 | M3 |
| 块级或方法级代码切分 | M3 |
| 检索指标对比（简单词法 vs BM25 Recall@K） | M3 |
| SQLite 持久化 | M4 |
| 3 个可复现 Spring Boot Bug 样本 | M4 |
| 评测 Runner 与指标报告 | M4 |
| Embedding 语义检索 | 后续 |
| Tree-sitter AST 解析 | 后续 |
| 自动代码补丁生成 | 阶段 3+ |
| Docker 沙箱 Maven 测试 | 阶段 3+ |
| 反思修正与人工审批（HITL） | 阶段 3+ |
| Vue 前端 | 阶段 2+ |
| Spring Boot 管理后端 + 用户/权限 | 阶段 2+ |
| MySQL / Redis / MinIO | 阶段 2+ |
| MCP 协议接入 | 阶段 4+ |
| Nginx / Docker Compose 生产部署 | 阶段 4+ |

## 3. 用户场景

### 3.1 最终用户场景（多阶段后）

开发者本地有一个 Spring Boot 项目，遇到 Bug：

1. 在前端提交项目路径、Issue 描述、错误日志
2. Agent 自动理解问题、规划排查、检索代码、推理根因
3. 输出结构化 JSON 报告 + Markdown 报告
4. 后续阶段：生成代码补丁、Docker 沙箱测试、反思修正、人工审批

### 3.2 M1 阶段用户场景

开发者通过 `POST /api/v1/tasks` 提交：

- `repository_path`：本地 Spring Boot 项目路径（必须位于 `ALLOW_ROOT` 子树内）
- `issue_description`：自然语言问题描述
- `error_log`：可选错误日志

Agent 完成确定性垂直切片：

- 校验输入
- 探索仓库（文件树 + 符号检索）
- 检索代码（关键词搜索 + 读文件）
- 生成基础报告

输出：task_id、状态查询、trace 查询、报告查询。

### 3.3 M0 阶段用户场景

无业务用户场景。M0 仅提供：

- `GET /api/v1/health` 健康检查
- 工程骨架可启动、可测试、可类型检查

## 4. 非功能性需求

### 4.1 可观测性

- 每次工具调用记录：工具名、参数、耗时、状态、结果摘要（≤500 字符）
- 每个节点记录：开始时间、结束时间、耗时
- Trace 持久化到存储层（M1 InMemory，M4 SQLite）

### 4.2 可评测

- 评测指标必须可量化、可复现
- 禁止伪造准确率或命中率数据
- 每条评测结果必须关联 `task_id` 可追溯

### 4.3 安全边界

- 工具只能读取 `repository_path` 子树内文件
- `repository_path` 必须位于 `ALLOW_ROOT` 内
- `read_file` 只接收 `relative_path`，不接收绝对路径
- 路径 canonicalize 后必须仍位于 `repository_path` 内

### 4.4 失败降级

- 工具失败不中断主流程，记录 `error` 到 Trace，由节点决定降级策略
- LLM 调用失败降级到确定性规则（M2 实现）
- 节点失败不中断整个 Graph，`status` 标记为 `failed`，仍输出部分报告

## 5. 排除项（明确不做）

- 不做聊天机器人或通用知识库问答
- 不做代码生成器或 Copilot 替代品
- 不做 IDE 插件
- 不做 CI/CD 工具
- 不做生产监控告警系统
