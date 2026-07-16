# 架构设计（Architecture）

## 1. 系统模块边界

```
┌─────────────────────────────────────────────────────────────┐
│                    前端层 (Vue 3 + TS)                       │ 阶段 2+
│  任务提交 / 诊断结果可视化 / 执行轨迹 / Monaco 报告查看       │
└─────────────────────────────────────────────────────────────┘
                              │ SSE / HTTP
┌─────────────────────────────────────────────────────────────┐
│              Java 业务后端 (Spring Boot 3 + Java 21)         │ 阶段 2+
│  用户/权限(JWT)│ 项目仓库管理│ 任务调度│ SSE 推送│ MinIO 文件│
└─────────────────────────────────────────────────────────────┘
                              │ HTTP / Redis Stream
┌─────────────────────────────────────────────────────────────┐
│              Python Agent 服务 (FastAPI + LangGraph)         │ M0+
│  LangGraph 编排│ Tool 实现│ 检索│ 根因分析│ 报告生成         │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│  存储层: MySQL(业务) + Redis(缓存/Stream) + MinIO(源码/报告) │
│         FAISS(向量检索) + SQLite(Agent 内部 trace)           │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│              沙箱层 (Docker SDK + Maven 测试)                │ 阶段 3+
└─────────────────────────────────────────────────────────────┘
```

M0 阶段仅实现：Python Agent 服务骨架（FastAPI app + 健康检查）+ 长期稳定的 Protocol。

## 2. 接口边界（M0 起定义，后续不动）

### 2.1 Tool Protocol

```python
@runtime_checkable
class Tool(Protocol):
    name: str
    description: str
    def run(self, params: dict, ctx: ToolContext) -> ToolResult: ...
```

### 2.2 TaskRepository Protocol

```python
class TaskRepository(Protocol):
    def create_task(self, ...) -> Task: ...
    def get_task(self, task_id: str) -> Task | None: ...
    def list_tasks(self) -> list[Task]: ...
    def update_status(self, task_id: str, status: TaskStatus) -> None: ...
    def save_trace(self, task_id: str, trace: Trace) -> None: ...
    def get_traces(self, task_id: str) -> list[Trace]: ...
    def save_report(self, task_id: str, report: Report) -> None: ...
    def get_report(self, task_id: str) -> Report | None: ...
```

实现：M1 `InMemoryTaskRepository`，M4 `SqliteTaskRepository`。

### 2.3 Tracer Protocol

```python
class Tracer(Protocol):
    def record_tool_call(self, task_id: str, call: ToolCall) -> None: ...
    def record_node_timing(self, task_id: str, timing: NodeTiming) -> None: ...
```

实现：M1 `InMemoryTracer`，M4 推送 Redis Stream。

### 2.4 LLMClient Protocol（M2 落地）

```python
class LLMClient(Protocol):
    def invoke(self, messages: list[LLMMessage]) -> LLMResponse: ...
```

实现：M2 `MockLLMClient` + `OpenAICompatibleClient`。

## 3. ToolContext 设计

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
- 路径校验逻辑统一放在 `tools/_path_safety.py`（M1 创建）

## 4. AgentState 演进策略

不一次性定义包含所有字段的超大 State。按阶段演进：

| 阶段 | 新增字段 |
|------|---------|
| M1 | 输入字段、validate_input 输出、explore_repository 输出、retrieve_code 输出、build_basic_report 输出、tool_calls、node_timings、errors、status、current_node |
| M2 | `issue_class`、`extracted_keywords`、`error_signature`、`plan_steps`、`plan_rationale`、`root_causes`、`analysis_summary` |
| M3 | 检索评分、代码块、检索元数据 |

每次新增字段必须有实际节点使用，不创建纯占位字段。

State 体积限制（M1 起强制）：

- 最多 10 个代码片段
- 每片段最多 60 行
- 每片段最多 4000 字符
- Trace `result_summary` 最多 500 字符
- 不保存完整文件
- State 总体积上限 100KB（初始值，后续根据真实运行数据调整）

## 5. 异步任务边界（M1 起强制）

```python
class TaskService:
    def submit_task(self, repository_path: str, issue_description: str, error_log: str | None) -> str:
        """创建 task_id 并通过进程内后台任务执行"""
        ...

    def run_task_sync(self, task_id: str) -> None:
        """同步执行,用于集成测试与 Graph 调试"""
        ...
```

架构约束（必须在 API 文档和 README 中明示）：

- 这是 MVP 临时方案
- 服务重启会丢失正在运行的任务
- 不支持多实例协调
- 后续由 Redis Stream 或任务队列替换

## 6. 工具调用规则（M1 起强制）

- 禁止在 Graph 中硬编码 `symbol_name="saveOrder"` 等样例符号
- `find_java_symbol` 的调用必须从 `error_log` Java 堆栈或 `issue_description` 中提取符号
- 符号提取规则：
  1. 优先从 `error_log` 的 Java 堆栈中提取类名和方法名
  2. 从 `issue_description` 中提取符合 Java 标识符特征的词
  3. 只有提取到明确符号时才调用 `find_java_symbol`
  4. 没有明确符号时跳过该工具
- Graph 必须适用于不同仓库和不同方法名

## 7. 检索评分规则（M1 起强制）

M1 `search_code` 实现简单确定性词法评分：

| 命中类型 | 权重 |
|---------|------|
| 普通关键词命中 | 基础分（1.0） |
| 类名命中 | 加权（2.0） |
| 方法名命中 | 加权（2.0） |
| 异常类名命中 | 加权（3.0） |
| Spring 注解命中 | 加权（2.5） |

- 按总分降序返回 Top K
- 无任何命中时返回空结果
- M1 不引入 `rank_bm25`
- M3 再实现 BM25，并通过同一批 Case 对比简单词法评分和 BM25 的 Recall@K

## 8. 示例 Bug 复现方式（M1 起强制）

示例事务 Bug 必须满足：

- 框架：Spring Boot + Spring Data JPA 或 JdbcTemplate + H2 内存数据库 + JUnit 5 + Spring Boot Test
- Bug 类型：同类内部调用绕过 Spring AOP 代理，导致 `@Transactional` 不生效
- 必须包含一个可独立运行的失败测试：`mvn test`
- 测试过程：
  1. 外部调用一个未加事务的方法
  2. 该方法通过 `this` 或直接方法调用，调用同类中带 `@Transactional` 的方法
  3. 内部方法写入数据库后抛出 `RuntimeException`
  4. 由于自调用绕过代理，预期的事务没有生效
  5. 测试通过数据库记录数量证明数据未按预期回滚
- sample README 必须记录：Bug 描述、预期行为、实际行为、根因、复现命令、预期失败测试名称
- Agent 不执行 Maven，测试仅用于人工验证样例 Bug 真实存在
- 自动执行 Maven 留到 Docker 沙箱阶段

## 9. 最终技术栈

### 前端（阶段 2+）

Vue 3、TypeScript、Vite、Element Plus、Pinia、Axios、SSE、Monaco Editor

### Java 业务后端（阶段 2+）

Java 21、Spring Boot 3、Spring MVC、MyBatis-Plus、MySQL、Redis、Redis Stream、Spring Security、JWT、SSE、MinIO

### Python Agent 服务（M0+）

Python 3.11+、FastAPI、Pydantic、Pydantic-Settings、Uvicorn、LangGraph（M1+）、LangChain（M2+）、FAISS（M3+）、BM25（M3+）、Tree-sitter（后续）、GitPython（后续）、Docker SDK（阶段 3+）

### 部署（阶段 4+）

Docker Compose、Nginx、MySQL、Redis、MinIO

## 10. M0 阶段技术栈（精简）

仅引入：

- FastAPI（Web 框架）
- Uvicorn（ASGI 服务器）
- Pydantic（数据模型）
- Pydantic-Settings（配置管理）
- HTTPX（测试客户端）
- Pytest（测试框架）
- Ruff（代码检查）
- MyPy（静态类型检查）

不引入：LangGraph、LangChain、Anthropic SDK、OpenAI SDK、rank_bm25、FAISS、Tree-sitter、SQLAlchemy、Redis、MinIO、Docker SDK。
