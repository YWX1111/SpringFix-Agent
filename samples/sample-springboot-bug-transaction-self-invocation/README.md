# Sample Bug: @Transactional self-invocation

示例 Spring Boot 项目，包含一个 **intentionally failing test** 用于证明
`@Transactional` 同类内部调用绕过 Spring AOP 代理导致事务失效的 Bug。

## Bug 描述

`OrderService.createOrder()` 是外部入口方法，**未** 标注 `@Transactional`。
它通过 `this.createOrderInTransaction()` 直接调用同类中的 `@Transactional`
方法。由于自调用绕过 Spring AOP 代理，`createOrderInTransaction` 上的
`@Transactional` 注解不会生效：

- 内部方法先 `INSERT` 一条订单
- 然后抛出 `RuntimeException`
- 预期：事务回滚，数据库中订单数为 0
- 实际：事务未生效，订单被持久化，数据库中订单数为 1

## 预期行为

调用 `createOrder()` 后，由于内部方法抛出异常且 `@Transactional`
应触发回滚，`orders` 表中记录数应为 **0**。

## 实际行为

由于 `createOrder()` 通过 `this` 调用 `createOrderInTransaction()`，
绕过 Spring AOP 代理，`@Transactional` 不生效。`INSERT` 立即提交，
即使后续抛出 `RuntimeException`，订单已无法回滚，`orders` 表中
记录数为 **1**。

## 技术根因

Spring 的 `@Transactional` 通过 AOP 代理实现。当外部调用者通过
Spring 容器获取 `OrderService` 的代理对象并调用其方法时，代理会
拦截调用并启动事务。但 `createOrder()` 在代理对象内部通过 `this`
直接调用 `createOrderInTransaction()`，`this` 引用的是目标对象自身
（不是代理），因此 `createOrderInTransaction` 上的 `@Transactional`
不会被拦截，事务不会启动。

修复方法（**不要在此 sample 中应用**）：
- 通过注入 `@Lazy` 自引用调用代理方法
- 通过 `AopContext.currentProxy()` 获取代理调用
- 将 `createOrderInTransaction` 提取到独立 Service
- 通过 `ApplicationContext.getBean(OrderService.class)` 获取代理

## 复现命令

```bash
cd samples/sample-springboot-bug-transaction-self-invocation
mvn test
```

**前提**：本地需安装 Java 17+ 和 Maven 3.6+。

设置 `JAVA_HOME` 指向 JDK 17：

Windows PowerShell：

```powershell
$env:JAVA_HOME = "C:\Program Files\Java\jdk-17"
mvn test
```

WSL / Linux / macOS：

```bash
export JAVA_HOME=/path/to/jdk-17
mvn test
```

## 预期失败测试名称

```
shouldRollbackOrderWhenInnerMethodThrows
```

完整测试类路径：

```
com.springfix.sample.transaction.TransactionSelfInvocationTest
       .shouldRollbackOrderWhenInnerMethodThrows
```

失败信息形如：

```
expected: <0> but was: <1>
Expected rollback but data was persisted;
self-invocation bypassed the @Transactional AOP proxy
```

## 为什么这个失败是 Benchmark 金标

- **失败来自目标断言**：`assertEquals(0, count, ...)` 在自调用绕过代理时
  必然失败，不是配置错误、依赖缺失或编译失败
- **不是项目损坏**：Maven 构建、Spring Boot 启动、H2 数据库初始化均正常，
  仅事务语义层面的金标测试失败
- **不修复**：本 sample 的存在意义是复现 Bug，SpringFix Agent 后续阶段
  需要能识别此类 Bug 并给出根因分析。修复 sample 会让金标失效

## 不要在主 Python 测试套件中执行该 Maven 测试

SpringFix Agent 的 Python 测试套件 **不会** 自动执行 `mvn test`。该
Maven 测试仅用于人工验证样例 Bug 真实存在。自动执行 Maven 留到
Docker 沙箱阶段（阶段 3+）。

## 技术栈

- Java 17
- Spring Boot 3.2.0
- spring-boot-starter-jdbc
- H2 内存数据库
- JUnit 5
- Spring Boot Test
