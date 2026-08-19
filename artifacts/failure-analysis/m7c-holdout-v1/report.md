# M7C：Frozen Holdout v1 Failure RCA

## 结论摘要

本 RCA 只分析已固化的 M7B Fresh Unseen Holdout v1 单次 Live 结果，不重新运行 Agent、LLM、Live、Holdout Agent 或 Holdout Mock，也不修改 SpringFix 生产代码、Prompt、Validator、Retrieval、Gold、Samples、Tests 或 Runtime。

- **CONFIRMED：** M7B 运行 `20260819T040252Z-9aa5957d` 在 7 个 case 中 Repair Success 为 `3/7 (42.86%)`；4 个失败分别落在编译、目标测试和 Proposal 边界。
- **CONFIRMED：** 没有 provider failure 或 infrastructure failure；失败是可观测的逻辑/语义修复失败。
- **CONFIRMED：** `missing-constructor-bean` 暴露出 Validator → E2E proposal gate 的确定性正确性边界问题：一个 import 不完整的多 edit proposal 被部分接受，剩余 edit 被应用，最终造成主源码编译失败。`PatchApplier` 对其收到的已验证 proposal 仍然是 all-or-nothing；问题发生在进入 Applier 之前。
- **CONFIRMED：** `invalid-config-property-value` 与 `wrong-active-profile` 都是已完整应用且可编译、但对目标 `ApplicationContextRunner` 不生效的配置语义修复。
- **LIKELY：** `ambiguous-request-mapping` 是 provider 成功返回结构化 `insufficient_evidence` 后的 proposal 过度 abstention；现有安全证据没有保留精确的 validated snippet 内容，因此“证据是否足以安全地产生 patch”保持 `UNKNOWN`。
- **CONFIRMED：** Diagnosis Benchmark 的 `category_match` 被记录，却没有进入 `case_pass` 门槛；因此 `wrong-active-profile` 与 `ambiguous-request-mapping` 的 issue-category mismatch 不会阻止 Diagnosis Benchmark Pass。这是评估指标语义不一致，不是这两个 case 的第一失败边界。
- **CONFIRMED：** Maven 观测中的 `affected_file` 可能落到 `java.lang.reflect.Method.invoke(Method.java` 这类框架栈帧，而非用户源码文件；这是 observability quality issue，不能作为根因证据。

## 基线与证据范围

| 项目 | 值 |
|---|---|
| Branch | `main` |
| Evidence commit | `a28e763c052dafa8a5459e5eeb56d44926faf466` |
| Runtime | `0.14.0` |
| M7B Run ID | `20260819T040252Z-9aa5957d` |
| Split | unseen holdout v1，7 cases |
| Provider / model | `openai_compatible / qwen3.7-plus` |
| Repair Success | `3/7` |
| Provider / infrastructure failure | `0 / 0` |

本 RCA 使用的输入只有：

- **CONFIRMED：** curated evidence：`artifacts/evaluation/m7b-holdout-v1/report.md`、`summary.json`、`run-metadata.json`。
- **CONFIRMED：** 原始 ignored Live evidence：`artifacts/end-to-end-repair/live/20260819T040252Z-9aa5957d/` 下的 case result、bounded metadata、patch 摘要和 Maven 观测字段。
- **CONFIRMED：** 当前仓库中 Validator、PatchApplier、E2E runner、benchmark evaluator 和目标 sample/test 的只读源码。
- **CONFIRMED：** 本文不复制 raw LLM response、full Prompt、full Maven output 或 full `patch.diff`；只保留脱敏后的相对路径、状态、计数和 bounded error summary。

## 端到端边界状态

下表按要求的顺序记录：Input/sanitized repo → Diagnosis → Retrieval/Evidence → Proposal → Patch Validation → Import Validation → Patch Application → Maven Compile → Surefire/Target Test → Repair Success。

| Case | Input / Diagnosis | Retrieval / Evidence | Proposal / Patch Validation | Import Validation | Application | Compile | Surefire / Target Test | Repair Success |
|---|---|---|---|---|---|---|---|---|
| `missing-constructor-bean` | **CONFIRMED：** baseline reproduced；Diagnosis completed，但 benchmark keyword coverage `0.50` 未达 `0.66` | **CONFIRMED：** evidence target recall `1.00`；expected file recall `1.00`，目标文件到 R@5 才出现 | **CONFIRMED：** proposal status `proposed`，validation gate passed；原 proposal 2 edits，1 edit 被拒、1 edit 留下 | **CONFIRMED：** import check `fail`，但未成为 proposal gate 的阻断条件 | **CONFIRMED：** 剩余 1 个 sanitized edit 被完整应用 | **CONFIRMED：** `main_compile_failure`，exit `1`，Surefire 未启动 | **CONFIRMED：** 未找到 target test；`0/0/0/0` | **CONFIRMED：** failed |
| `invalid-config-property-value` | **CONFIRMED：** baseline reproduced；Diagnosis benchmark passed | **CONFIRMED：** R@1/R@3/R@5 true；evidence target recall `1.00` | **CONFIRMED：** proposal、validation、application 均通过 | **CONFIRMED：** Java import not applicable | **CONFIRMED：** edit 完整应用，单文件变更 | **CONFIRMED：** compile success | **CONFIRMED：** target test 执行，`1` failure，分类 `test_failure` | **CONFIRMED：** failed |
| `wrong-active-profile` | **CONFIRMED：** baseline reproduced；Diagnosis benchmark passed；category mismatch 被单独记录 | **CONFIRMED：** R@1/R@3/R@5 true；evidence target recall `1.00` | **CONFIRMED：** proposal、validation、application 均通过 | **CONFIRMED：** Java import not applicable | **CONFIRMED：** edit 完整应用，单文件变更 | **CONFIRMED：** compile success | **CONFIRMED：** target test 执行，`1` failure，分类 `test_failure` | **CONFIRMED：** failed |
| `ambiguous-request-mapping` | **CONFIRMED：** baseline reproduced；Diagnosis benchmark passed；category mismatch 被单独记录 | **CONFIRMED：** R@1/R@3/R@5 true；expected file/evidence target recall `1.00` | **CONFIRMED：** provider completed，结构化 parse/schema 成功，但返回 `insufficient_evidence`，0 edits | **CONFIRMED：** not reached | **CONFIRMED：** not reached | **CONFIRMED：** not run | **CONFIRMED：** not run | **CONFIRMED：** failed |

## RCA Matrix

| Case | First failing boundary | Direct failure | Confirmed root cause | Contributing factors | Retrieval bottleneck? | Diagnosis problem? | Proposal problem? | Validator problem? | Application problem? | Compile/Test problem? | Framework defect? | LLM quality issue? | Confidence |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `missing-constructor-bean` | **CONFIRMED：** Maven Compile | **CONFIRMED：** duplicate `AuditClient` declaration及相关 method/override 不一致，主源码编译失败 | **CONFIRMED：** import-aware validation 拒绝了一个依赖 `Component` 的 edit，却保留另一个 edit；E2E gate 只要求“仍有 accepted edit”，未因 import failure 阻断，于是错误的 residual edit 被应用 | **CONFIRMED：** provider proposal 同时包含 import 不完整 edit 与错误的 duplicate-interface edit；**CONFIRMED：** Diagnosis keyword coverage 仅 `0.50` | **PARTIAL / CONFIRMED：** 目标文件只在 R@5 命中，但 evidence recall 仍为 `1.00`，不是第一失败边界 | **CONFIRMED：** benchmark coverage miss；**LIKELY：** 不是造成编译失败的唯一原因 | **CONFIRMED：** 原始 proposal 含错误 edit；**CONFIRMED：** import failure 未阻断 proposal | **CONFIRMED：** rejected edit 与 accepted edit 可被拆开，`passed` 不要求 rejected count 为 0 | **CONFIRMED：** no；Applier 对其收到的 sanitized proposal 完整应用 | **CONFIRMED：** compile failure 是直接观测结果，不是根因归属 | **CONFIRMED：** Validator/E2E boundary 存在确定性 correctness gap | **CONFIRMED：** provider 产出了错误的 multi-edit proposal | **CONFIRMED：** 高 |
| `invalid-config-property-value` | **CONFIRMED：** Surefire / Target Test | **CONFIRMED：** target test 仍因 configuration binding failure 失败 | **CONFIRMED：** `application.yml` 中 `billing.max-retries: 0 → 1` 虽满足 `@Min(1)`，但目标 `ApplicationContextRunner` 测试没有提供 property values；已应用的文件变更没有改变该 runner 观察到的 binding input | **LIKELY：** Gold/fixture 同时允许配置文件路径，造成“文件值正确但测试入口不消费”的 contract tension | **CONFIRMED：** no；R@1/R@3/R@5 true | **CONFIRMED：** no direct diagnosis miss；coverage `0.75`、status/category/targets 足够 | **CONFIRMED：** patch semantic source selection 不正确 | **CONFIRMED：** no evidence of validator rejection or import issue | **CONFIRMED：** no；edit 完整应用 | **CONFIRMED：** compile passed，target test remained failing | **CONFIRMED：** no framework defect shown | **CONFIRMED：** patch 对当前测试入口语义无效 | **CONFIRMED：** 高 |
| `wrong-active-profile` | **CONFIRMED：** Surefire / Target Test | **CONFIRMED：** target test 仍运行在 `test` profile，`ProductionCatalog` 不可用，测试失败 | **CONFIRMED：** patch 将 `application.yml` active profile 改为 `production`，但目标测试显式 `.withPropertyValues("spring.profiles.active=test")`；该 edit 不控制测试实际使用的 profile | **LIKELY：** Gold/fixture 允许的配置文件 edit 与测试显式 property override 形成 contract tension | **CONFIRMED：** no；R@1/R@3/R@5 true | **CONFIRMED：** no direct diagnosis miss；coverage `0.75`、status/targets 足够；**UNKNOWN：** exact agent category 未由安全 artifact 保留 | **CONFIRMED：** patch semantic source selection 不正确 | **CONFIRMED：** no evidence of validator rejection or import issue | **CONFIRMED：** no；edit 完整应用 | **CONFIRMED：** compile passed，target test remained failing | **CONFIRMED：** no framework defect shown | **CONFIRMED：** patch 对显式 property override 无效 | **CONFIRMED：** 高 |
| `ambiguous-request-mapping` | **CONFIRMED：** Proposal | **CONFIRMED：** provider 返回 `insufficient_evidence`，无 patch，因此没有进入验证/应用/Maven | **LIKELY：** 在 provider completed、schema valid、retrieval metrics 全通过的情况下，proposal 层发生 over-abstention | **UNKNOWN：** 安全 artifact 未保存两段 validated evidence 的精确内容，无法证明其是否足以安全构造双文件 patch | **CONFIRMED：** no at evaluator metric level；R@1/R@3/R@5、file/evidence recall 全通过 | **CONFIRMED：** no direct diagnosis gate miss；**UNKNOWN：** actual issue category | **LIKELY：** no-edit abstention likely过严 | **UNKNOWN：** no import validation reached | **CONFIRMED：** not reached | **CONFIRMED：** not reached；Maven not run | **CONFIRMED：** no framework defect shown | **LIKELY：** proposal calibration / evidence sufficiency judgment issue | **LIKELY：** 中 |

## 1. `missing-constructor-bean`：Compile correctness

- **CONFIRMED：** 原始源码中的 `AuditClient` 已经是一个包含 `record(String)` 的 interface；`EmailAuditClient` 实现该 interface，`NotificationService` 构造注入 `AuditClient`。
- **CONFIRMED：** raw evidence 记录了原 proposal 有 2 edits；其中一个 edit 因缺少所需 import / unresolved symbol 被拒，另一个 edit 被保留并应用。
- **CONFIRMED：** `PatchValidationResult.passed` 的当前语义是 `proposal.status == proposed` 且 `accepted_edit_count > 0`；它不要求 `rejected_edit_count == 0`，也不把 import check failure 作为独立阻断条件。
- **CONFIRMED：** E2E runner 将 `import_check_status` 作为 metrics/telemetry 记录，但 `proposal_valid` 主要依赖 `validation.passed` 与 forbidden-file 检查。因此 import failure 可以与 proposal-valid 同时出现。
- **CONFIRMED：** `PatchApplier` 收到的是经过 Validator 筛选后的 sanitized proposal；它对这个输入做 preflight 和 all-or-nothing apply。故本 case 不是 Applier 在同一 proposal 内“半应用”，而是 Validator 先将 proposal 变成了错误的可应用子集。
- **CONFIRMED：** 应用后的 residual edit 造成 duplicate `AuditClient` class，以及 method/override 不一致；Maven 在主源码编译阶段失败，Surefire 没有启动。
- **CONFIRMED：** 这是本批最明确的 framework correctness candidate：语义相关的 rejected edit 与 accepted edit 被拆开后仍能越过 proposal gate。该结论只记录 RCA，不在本轮实现修复。

## 2. `invalid-config-property-value`：Semantic repair correctness

- **CONFIRMED：** Gold-facing constraint 是 `billing.max-retries` 至少为 `1`；应用的 `0 → 1` 值本身满足 `@Min(1)`。
- **CONFIRMED：** patch 只修改了 `src/main/resources/application.yml`，编译成功，说明 application/compile integrity 均通过。
- **CONFIRMED：** target test 使用 `ApplicationContextRunner`，仅通过 `withUserConfiguration(Application.class)` 建立上下文，没有提供 property values；patched run 仍报告 binding failure。
- **CONFIRMED：** 因此失败点不是数值错误、路径越界、import 错误或 partial application，而是修复没有命中目标测试实际使用的 configuration input。
- **LIKELY：** 这里存在 fixture contract tension：允许的 Gold 文件路径与 target test 的配置注入方式未完全对齐。证据不足以把它归为 framework defect；当前应优先标为 patch semantic / LLM quality issue。

## 3. `wrong-active-profile`：Semantic repair correctness

- **CONFIRMED：** `ProductionCatalog` 只在 `production` profile 下启用，`CatalogService` 依赖它。
- **CONFIRMED：** patch 将 `application.yml` 的默认 active profile 从 `test` 改为 `production`，并且 compile 成功。
- **CONFIRMED：** target test 明确设置 `.withPropertyValues("spring.profiles.active=test")`；因此测试运行时仍使用 `test`，Production-only bean 不可用，target test failure 保留。
- **CONFIRMED：** 这是已应用 patch 的 semantic source/override mismatch，不是 Validator、Applier 或 Maven compile defect。
- **CONFIRMED：** evaluator 记录了 `issue_category_match=false`，但 `Diagnosis Benchmark Pass` 的 `case_pass` 公式没有纳入 `category_match`；这解释了为什么诊断可 pass 而 category mismatch 仍存在。
- **UNKNOWN：** 当前安全 artifact 未保存 agent 结构化输出中的精确 issue category，不能推断它实际返回了哪一个 category。

## 4. `ambiguous-request-mapping`：Proposal abstention

- **CONFIRMED：** baseline failure 是两个 controller 对同一 GET route 产生 ambiguous mapping；expected files 为 `ReportController.java` 与 `SummaryController.java`。
- **CONFIRMED：** retrieval metrics 全通过：R@1/R@3/R@5 为 true，expected file recall 与 evidence target recall 均为 `1.00`；validated evidence count 为 `2`，rejected evidence count 为 `0`。
- **CONFIRMED：** provider completed，结构化 parse/schema 成功，未发生 provider、HTTP、schema 或 infrastructure failure；但返回 `insufficient_evidence`，response edit count 为 `0`。
- **LIKELY：** 在 evaluator-level evidence 指标已满足的前提下，这是 proposal over-abstention，而非 retrieval 召回失败。
- **UNKNOWN：** 安全 artifact 没有保存两段 validated evidence 的原文，因此不能断言 provider 面对的确切证据一定足以构造一个安全的两文件 patch。该未知项限制了对“合理 abstention”与“LLM 质量问题”的强度判断。
- **CONFIRMED：** 因 proposal 未通过 proposed 状态，后续 Patch Validation、Patch Application、Maven Compile 和 Target Test 都没有执行；这里不是测试基础设施失败。

## Retrieval 与 Diagnosis RCA

### Retrieval / Evidence

| Case | R@1 / R@3 / R@5 | Expected file recall | Evidence target recall | 结论 |
|---|---|---:|---:|---|
| `missing-constructor-bean` | false / false / true | 1.00 | 1.00 | **PARTIAL / CONFIRMED：** rank quality 有弱点，目标文件在 R@5 才出现；但已取得目标证据，不是直接失败边界 |
| `invalid-config-property-value` | true / true / true | 0.6667 | 1.00 | **CONFIRMED：** no retrieval bottleneck for observed failure |
| `wrong-active-profile` | true / true / true | 0.6667 | 1.00 | **CONFIRMED：** no retrieval bottleneck for observed failure |
| `ambiguous-request-mapping` | true / true / true | 1.00 | 1.00 | **CONFIRMED：** no retrieval bottleneck at evaluator metric level；**UNKNOWN：** exact snippet sufficiency |

- **CONFIRMED：** 4 个失败 case 中，只有 `missing-constructor-bean` 显示出 retrieval ranking weakness；它仍完成 proposal、application 并进入 compile，因此不能把该 weakness 当成其主根因。
- **CONFIRMED：** 其余三个失败均至少在 evaluator-level R@1/R@3/R@5 上满足，M7B failure pattern 不支持“全局 retrieval 失效”的结论。

### Diagnosis

| Case | Diagnosis benchmark | Coverage | Category match | Status / target evidence | 结论 |
|---|---|---:|---:|---|---|
| `missing-constructor-bean` | fail | 0.50 | true | status 与 target evidence 满足 | **CONFIRMED：** 有 keyword-coverage metric miss；**LIKELY：** 不是后续 compile failure 的唯一原因 |
| `invalid-config-property-value` | pass | 0.75 | true | status 与 target evidence 满足 | **CONFIRMED：** no direct diagnosis bottleneck |
| `wrong-active-profile` | pass | 0.75 | false | status 与 target evidence 满足 | **CONFIRMED：** category mismatch 被报告但不影响 case_pass；**UNKNOWN：** actual category |
| `ambiguous-request-mapping` | pass | 0.75 | false | status 与 target evidence 满足 | **CONFIRMED：** category mismatch 被报告但不影响 case_pass；**UNKNOWN：** actual category |

- **CONFIRMED：** evaluator 的 `case_pass` 需要 agent completed、diagnosis status match、coverage ≥ `0.66`、expected file/target hits 和无 invalid rejected evidence，但没有 `category_match` 条件。
- **CONFIRMED：** 因此 `wrong-active-profile` 与 `ambiguous-request-mapping` 的 `issue_category_match=false` 是独立的 evaluation metric inconsistency，不能被解释为它们的 first failing boundary。

## Validator、Application 与 Maven 观测语义

- **CONFIRMED：** Validator 会逐 edit 检查 path、evidence、range、old code、dangerous edit 和 Java import completeness；import failure 可将相关 edit 放入 rejected audit，同时保留其他 accepted edit。
- **CONFIRMED：** Generator 会把 `missing_required_import` 记录在 proposal audit，但只要仍有 accepted edit，最终 status 仍可能是 `proposed`，并让 `validation.passed` 为 true。
- **CONFIRMED：** E2E runner 的 `proposal_valid` 没有把“任何 original edit 被拒”作为统一阻断条件；`all_edits_applied` 统计的是传给 Applier 的 sanitized proposal，而不是原始 provider response 的 edit 数量。
- **CONFIRMED：** 因此 missing case 的应用层指标可以同时显示 `patch_applied=true`、`all_edits_applied=true` 和原始 proposal `rejected_edit_count=1`；这不是数据矛盾，而是两个 proposal 边界的计数口径不同。
- **CONFIRMED：** invalid-config 与 wrong-profile 没有 import failure、rejected edit 或 application rollback 证据；它们的失败发生在目标 test 语义验证。
- **CONFIRMED：** missing case 的 failure reason `surefire_report_missing` 是因为 compile failure 后没有 Surefire report；更上游、更准确的 classifier 是 `main_compile_failure`。二者应在 observability 中明确区分。
- **CONFIRMED：** Maven `affected_file` 观测曾提取到 framework stack frame `java.lang.reflect.Method.invoke(Method.java`；该值不是可靠的 user-source affected file。
- **CONFIRMED：** ambiguous case 没有执行 Maven；不能从它推断 compile/test 或 infrastructure 状态。

## M7C Failure Taxonomy

| Taxonomy | Cases | 判断 |
|---|---|---|
| A. Compile correctness | `missing-constructor-bean` | **CONFIRMED：** residual invalid edit 造成主源码编译失败；上游 validator/E2E boundary 是可操作的根因候选 |
| B. Semantic repair correctness | `invalid-config-property-value`, `wrong-active-profile` | **CONFIRMED：** patch 完整应用并可编译，但未改变目标 test 的实际 configuration input |
| C. Proposal abstention | `ambiguous-request-mapping` | **LIKELY：** provider 在 evaluator metrics 已满足时返回 insufficient evidence；精确 snippet sufficiency 为 UNKNOWN |
| D. Evaluation metric inconsistency | `wrong-active-profile`, `ambiguous-request-mapping` | **CONFIRMED：** category_match 被报告却不参与 Diagnosis `case_pass` |
| E. Observability quality issue | missing failure reason / affected file fields | **CONFIRMED：** downstream report reason 与 upstream classifier 未分层，affected file 可误指 framework stack frame |

## Framework defect 与 LLM quality attribution

- **CONFIRMED：** `missing-constructor-bean` 有确定性的 framework correctness gap，位置在 Validator → E2E proposal boundary；LLM 同时对 proposal 内容质量负责，但不能用 LLM 质量掩盖该 boundary 的 partial-acceptance 语义。
- **CONFIRMED：** `invalid-config-property-value` 与 `wrong-active-profile` 的应用、编译和 import 路径均正常；现有证据支持 patch semantic / LLM quality attribution，不支持 framework defect attribution。
- **LIKELY：** `ambiguous-request-mapping` 的主要 attribution 是 LLM proposal calibration / evidence sufficiency judgment；因为 exact validated snippets 未保留，不能升级为高置信度确定结论。
- **CONFIRMED：** evaluator category mismatch 是评估语义问题；它与上述 semantic patch failure、proposal abstention 是不同维度，不能混并成单一模型或框架根因。

## Follow-up priorities（只列候选，不实施）

### P0：确定性 framework correctness candidate

- **CONFIRMED：** 评估并补充“原始 proposal 含 rejected edit 时是否允许 proposal gate 通过”的明确不变量；特别覆盖 Java import failure 与语义相关 multi-edit。
- **CONFIRMED：** 评估 Validator/E2E 是否需要保留 edit lineage，并让 rejected required edit 阻止剩余 dependent edit 进入 Applier；本轮不改变 Validator。
- **CONFIRMED：** 评估 Maven classifier 的 source-file extraction，禁止把 framework stack frame 作为 affected source file；同时分离 `main_compile_failure` 与 `surefire_report_missing`。

### P1：通用 correctness guard 与评估契约

- **LIKELY：** 增加 config/profile source-of-truth 语义检查候选：识别 `ApplicationContextRunner` 的显式 property override，以及 patch 到 `application.yml` 对该测试入口可能无效的情况。
- **CONFIRMED：** 对 evaluator 的 `category_match` 是否应纳入 Diagnosis Benchmark Pass 做契约决策，并为 category mismatch 与 diagnosis status match 分别保留指标。
- **LIKELY：** 增加“compile passed 但 target test 仍保留原 failure”的结构化 semantic-failure guard；不把它误报成 framework/infrastructure failure。

### P2：LLM / proposal quality candidate

- **LIKELY：** 优化 multi-edit proposal 的 import-aware consistency 与 duplicate-symbol avoidance；要求模型在同一语义修复中保持 edits 可共同落地。
- **LIKELY：** 优化 config/profile 场景的 source selection 与 explicit test override 识别。
- **LIKELY：** 校准 evidence sufficiency / abstention，使 ambiguous mapping 在证据充足时提出最小、安全的双文件 proposal，同时保留真正不足证据时的 abstention。

## Post-RCA verification

- **CONFIRMED：** `uv run python scripts/holdout_integrity.py`：PASS。
- **CONFIRMED：** `uv lock --check`：PASS。
- **CONFIRMED：** `uv run ruff check src/ tests/ scripts/`：PASS。
- **CONFIRMED：** `uv run mypy --strict src/`：PASS，94 source files，无 issues。
- **CONFIRMED：** `uv run pytest tests/ -q`：438 passed，1 skipped。
- **CONFIRMED：** 未运行任何 Live、Holdout Agent 或 Holdout Mock。

## 安全性与执行边界

- **CONFIRMED：** RCA artifacts 只包含脱敏后的 relative paths、bounded summaries、状态、计数和分类。
- **CONFIRMED：** 未写入任何 credential material、absolute local path、raw LLM response、full Prompt、full Maven output 或 full patch diff。
- **CONFIRMED：** 本轮不启动 M7B Live、不启动 Holdout Agent、不启动 Holdout Mock、不进入 M7D。
- **CONFIRMED：** 本轮不 commit、push、tag；预期只有新的 RCA artifact 目录保持 untracked。
