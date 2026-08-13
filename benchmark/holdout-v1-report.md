# Holdout v1 Diversity Report

This report describes the frozen holdout inventory at a category level. It
does not disclose diagnosis keywords, expected files, or repair concepts.

| Case | High-level category | Failure lifecycle | Primary subsystem |
|---|---|---|---|
| `missing-constructor-bean` | missing dependency bean | context startup | dependency injection |
| `constructor-circular-dependency` | constructor dependency cycle | context startup | dependency injection |
| `invalid-config-property-value` | invalid validated property value | context startup | configuration binding |
| `wrong-active-profile` | profile-conditioned bean unavailable | context startup | configuration/profile |
| `component-scan-boundary` | component outside discovery boundary | context startup | component scanning |
| `transaction-proxy-visibility` | ineffective transaction proxy boundary | test runtime | transaction AOP |
| `ambiguous-request-mapping` | duplicate HTTP handler route | context startup | Spring MVC |

Holdout v1 contains seven cases with distinct primary failure categories. The
three legacy development cases remain separate and are not part of this
diversity count.
