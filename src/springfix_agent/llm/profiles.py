"""Mock Profile: pre-configured LLM response sets for tests and demos.

A Profile bundles deterministic responses for IssueParser, TaskPlanner
and RootCauseAnalyzer so tests can exercise specific code paths
(happy path, insufficient evidence, invalid evidence, timeout,
invalid JSON) without depending on a real model.

Profiles are test-only; production code never references them.

Profile summary:

- ``happy_path``: transaction category + 3-step plan + complete RCA
  with one candidate whose evidence points at the sample fixture's
  OrderService.java (lines 1-20). Used for end-to-end demo runs.
- ``insufficient_evidence``: transaction category + 3-step plan +
  RCA with ``diagnosis_status=insufficient_evidence`` and no
  candidates. Exercises the "no evidence" degradation path.
- ``invalid_evidence``: RCA with one candidate whose evidence references
  a file not in retrieved_snippets. Exercises the evidence rejection
  audit path.
- ``timeout``: every LLM call raises RetryableError. Exercises the
  fallback paths of all three LLM nodes.
- ``invalid_json``: every LLM call raises SchemaValidationError.
  Exercises the schema-repair-then-fail path.

The three ``benchmark_*`` profiles are offline fixture responses for M4C.
They validate the Runner and evaluator; they are not model-quality results.
"""

from __future__ import annotations

from collections.abc import Callable

from pydantic import BaseModel

from springfix_agent.llm._retry import RetryableError, SchemaValidationError
from springfix_agent.llm.schemas import (
    EvidenceReference,
    InvestigationPlan,
    InvestigationStep,
    IssueAnalysis,
    RootCauseAnalysis,
    RootCauseCandidate,
)
from springfix_agent.llm.trace import LLMCall

ProfileName = str

# File path and line range that the happy_path Profile's evidence points at.
# This matches the sample_repo fixture's OrderService.java layout; it is a
# test fixture reference, not a production hardcoded answer.
HAPPY_PATH_FILE = "src/main/java/com/example/OrderService.java"
HAPPY_PATH_LINES: tuple[int, int] = (1, 20)


def _happy_path_issue() -> IssueAnalysis:
    return IssueAnalysis(
        issue_category="transaction",
        summary="Transactional self-invocation bypass",
        symptoms=["data not rolled back after exception"],
        exception_types=["RuntimeException"],
        extracted_symbols=["OrderService", "createOrder"],
        search_terms=["@Transactional", "createOrder"],
        spring_concepts=["AOP proxy", "self-invocation"],
    )


def _happy_path_plan() -> InvestigationPlan:
    return InvestigationPlan(
        steps=[
            InvestigationStep(
                step_id=1,
                objective="Browse repository structure",
                rationale="Identify Spring service beans and transactional boundaries.",
                search_terms=["@Service", "@Transactional"],
                target_symbols=["OrderService"],
                expected_evidence=["Service class with @Transactional method"],
            ),
            InvestigationStep(
                step_id=2,
                objective="Locate createOrder call chain",
                rationale="Trace how the public entry point reaches the transactional method.",
                search_terms=["createOrder"],
                target_symbols=["createOrder", "createOrderInTransaction"],
                expected_evidence=["Direct self-invocation of @Transactional method"],
            ),
            InvestigationStep(
                step_id=3,
                objective="Read OrderService implementation",
                rationale="Confirm whether the @Transactional method is called via this.",
                search_terms=["this"],
                target_symbols=["OrderService"],
                expected_evidence=["Method body with jdbcTemplate.update and exception throw"],
            ),
        ]
    )


def _happy_path_rca() -> RootCauseAnalysis:
    return RootCauseAnalysis(
        diagnosis_status="complete",
        summary="Spring AOP proxy bypassed via self-invocation of @Transactional method",
        candidates=[
            RootCauseCandidate(
                title="Spring @Transactional self-invocation bypass",
                description=(
                    "createOrder calls createOrderInTransaction directly via this, "
                    "bypassing the Spring AOP proxy. The @Transactional annotation "
                    "on the inner method has no effect, so the jdbcTemplate.update "
                    "is committed despite the thrown RuntimeException."
                ),
                confidence="high",
                evidence=[
                    EvidenceReference(
                        file=HAPPY_PATH_FILE,
                        start_line=HAPPY_PATH_LINES[0],
                        end_line=HAPPY_PATH_LINES[1],
                        explanation=(
                            "OrderService.createOrder directly invokes "
                            "createOrderInTransaction via this, bypassing the proxy."
                        ),
                    )
                ],
                recommended_fix=(
                    "Move the @Transactional method to a separate Spring bean and "
                    "inject it into OrderService, or use self-injection to obtain "
                    "the proxy. Do not call transactional methods via this."
                ),
                verification_steps=[
                    "Confirm OrderService.createOrder does not go through the proxy",
                    "Check whether any other service calls createOrderInTransaction directly",
                ],
            )
        ],
        missing_information=[],
    )


def _insufficient_issue() -> IssueAnalysis:
    return IssueAnalysis(
        issue_category="unknown",
        summary="Insufficient evidence to classify the reported problem",
        symptoms=["reported symptoms do not match any code in the repository"],
        exception_types=[],
        extracted_symbols=[],
        search_terms=[],
        spring_concepts=[],
    )


def _insufficient_plan() -> InvestigationPlan:
    return InvestigationPlan(
        steps=[
            InvestigationStep(
                step_id=1,
                objective="Search repository for mentioned concepts",
                rationale="Verify whether the reported subsystem exists in code.",
            ),
            InvestigationStep(
                step_id=2,
                objective="Read top candidate files",
                rationale="Collect whatever evidence is available.",
            ),
            InvestigationStep(
                step_id=3,
                objective="Report insufficient evidence",
                rationale="Be honest about missing context rather than fabricating.",
            ),
        ]
    )


def _insufficient_rca() -> RootCauseAnalysis:
    return RootCauseAnalysis(
        diagnosis_status="insufficient_evidence",
        summary="No code evidence found for the reported problem in this repository.",
        candidates=[],
        missing_information=[
            "Reported subsystem is not present in the repository",
            "No logs or stack trace referencing the subsystem",
        ],
    )


def _invalid_evidence_rca() -> RootCauseAnalysis:
    return RootCauseAnalysis(
        diagnosis_status="complete",
        summary="Model fabricated evidence referencing a file not in retrieved_snippets.",
        candidates=[
            RootCauseCandidate(
                title="Fabricated candidate",
                description="Evidence file does not exist in retrieved_snippets.",
                confidence="high",
                evidence=[
                    EvidenceReference(
                        file="NonExistentService.java",
                        start_line=1,
                        end_line=10,
                        explanation="This file does not exist in the repository.",
                    )
                ],
                recommended_fix="This candidate should be dropped by the validator.",
            )
        ],
    )


def _benchmark_transaction_issue() -> IssueAnalysis:
    return IssueAnalysis(
        issue_category="transaction",
        summary="Spring AOP transaction is bypassed by an internal service call.",
        symptoms=["the inserted order remains after the exception"],
        exception_types=["RuntimeException"],
        extracted_symbols=["OrderService", "createOrder", "createOrderInTransaction"],
        search_terms=["@Transactional", "self-invocation", "createOrder"],
        spring_concepts=["Spring AOP", "proxy", "self-invocation"],
    )


def _benchmark_transaction_plan() -> InvestigationPlan:
    return InvestigationPlan(
        steps=[
            InvestigationStep(
                step_id=1,
                objective="Locate the order service and transaction annotations",
                rationale="Inspect the service boundary and transactional method.",
                search_terms=["OrderService", "@Transactional"],
                target_symbols=["OrderService"],
            ),
            InvestigationStep(
                step_id=2,
                objective="Trace the createOrder call chain",
                rationale="Check whether the inner method is called through a proxy.",
                search_terms=["createOrder", "createOrderInTransaction"],
                target_symbols=["createOrder", "createOrderInTransaction"],
            ),
            InvestigationStep(
                step_id=3,
                objective="Compare the exception and transaction behavior",
                rationale="Connect the direct call to the committed insert.",
                search_terms=["RuntimeException", "this"],
                target_symbols=["OrderService"],
            ),
        ]
    )


def _benchmark_transaction_rca() -> RootCauseAnalysis:
    return RootCauseAnalysis(
        diagnosis_status="complete",
        summary="Spring AOP proxy bypassed because createOrder self-invokes the @Transactional method.",
        candidates=[
            RootCauseCandidate(
                title="Transactional self-invocation bypasses Spring AOP",
                description=(
                    "createOrder calls createOrderInTransaction directly on the same object. "
                    "That self-invocation bypasses the Spring AOP proxy, so @Transactional "
                    "does not create the rollback boundary."
                ),
                confidence="high",
                evidence=[
                    EvidenceReference(
                        file="src/main/java/com/springfix/sample/transaction/service/OrderService.java",
                        start_line=31,
                        end_line=37,
                        explanation="The public method directly calls the annotated inner method.",
                    )
                ],
                recommended_fix="Move the transactional operation to another Spring bean or call it through the proxy.",
            )
        ],
    )


def _benchmark_bean_issue() -> IssueAnalysis:
    return IssueAnalysis(
        issue_category="dependency_injection",
        summary="Spring cannot choose one PaymentGateway bean for CheckoutService.",
        symptoms=["application context startup fails"],
        exception_types=["NoUniqueBeanDefinitionException"],
        extracted_symbols=[
            "PaymentGateway",
            "StripePaymentGateway",
            "PaypalPaymentGateway",
            "CheckoutService",
        ],
        search_terms=["PaymentGateway", "@Qualifier", "@Primary"],
        spring_concepts=["dependency injection", "bean resolution"],
    )


def _benchmark_bean_plan() -> InvestigationPlan:
    return InvestigationPlan(
        steps=[
            InvestigationStep(
                step_id=1,
                objective="Find the PaymentGateway abstraction and implementations",
                rationale="Count candidate beans registered for the same type.",
                search_terms=["PaymentGateway", "@Component"],
                target_symbols=["PaymentGateway", "StripePaymentGateway", "PaypalPaymentGateway"],
            ),
            InvestigationStep(
                step_id=2,
                objective="Inspect CheckoutService constructor injection",
                rationale="Confirm the ambiguous dependency is injected without a qualifier.",
                search_terms=["CheckoutService", "@Qualifier", "@Primary"],
                target_symbols=["CheckoutService"],
            ),
            InvestigationStep(
                step_id=3,
                objective="Explain deterministic bean selection options",
                rationale="Relate the two beans to the startup exception and fixes.",
                search_terms=["NoUniqueBeanDefinitionException"],
            ),
        ]
    )


def _benchmark_bean_rca() -> RootCauseAnalysis:
    return RootCauseAnalysis(
        diagnosis_status="complete",
        summary="Two PaymentGateway beans match one CheckoutService dependency, causing NoUniqueBeanDefinitionException.",
        candidates=[
            RootCauseCandidate(
                title="Ambiguous PaymentGateway dependency injection",
                description=(
                    "StripePaymentGateway and PaypalPaymentGateway are both component beans "
                    "implementing PaymentGateway, while CheckoutService requests the interface "
                    "without @Qualifier or @Primary."
                ),
                confidence="high",
                evidence=[
                    EvidenceReference(
                        file="src/main/java/com/springfix/sample/beans/gateway/PaymentGateway.java",
                        start_line=4,
                        end_line=6,
                        explanation="PaymentGateway declares the shared pay contract.",
                    ),
                    EvidenceReference(
                        file="src/main/java/com/springfix/sample/beans/service/CheckoutService.java",
                        start_line=3,
                        end_line=13,
                        explanation="CheckoutService injects the interface without a selector.",
                    ),
                ],
                recommended_fix="Select one implementation with @Qualifier or mark one bean @Primary.",
            )
        ],
    )


def _benchmark_config_issue() -> IssueAnalysis:
    return IssueAnalysis(
        issue_category="configuration",
        summary="The ConfigurationProperties prefix does not match the YAML path.",
        symptoms=["the configured timeout is not bound"],
        exception_types=[],
        extracted_symbols=["MailProperties", "timeoutSeconds", "MailService"],
        search_terms=["ConfigurationProperties", "springfix.mail", "springfix.email"],
        spring_concepts=["@ConfigurationProperties"],
    )


def _benchmark_config_plan() -> InvestigationPlan:
    return InvestigationPlan(
        steps=[
            InvestigationStep(
                step_id=1,
                objective="Inspect MailProperties binding metadata",
                rationale="Read the declared prefix and bound property field.",
                search_terms=["@ConfigurationProperties", "MailProperties"],
                target_symbols=["MailProperties", "timeoutSeconds"],
            ),
            InvestigationStep(
                step_id=2,
                objective="Compare the YAML hierarchy with the Java prefix",
                rationale="Check whether mail and email use the same path.",
                search_terms=["springfix.mail", "springfix.email", "timeout-seconds"],
            ),
            InvestigationStep(
                step_id=3,
                objective="Trace the bound value consumer",
                rationale="Confirm MailService reads the affected property.",
                search_terms=["MailService", "timeoutSeconds"],
                target_symbols=["MailService"],
            ),
        ]
    )


def _benchmark_config_rca() -> RootCauseAnalysis:
    return RootCauseAnalysis(
        diagnosis_status="complete",
        summary="ConfigurationProperties declares springfix.mail while application.yml uses springfix.email, so timeoutSeconds stays at its default.",
        candidates=[
            RootCauseCandidate(
                title="ConfigurationProperties prefix mismatch",
                description=(
                    "MailProperties uses @ConfigurationProperties(prefix = \"springfix.mail\"), "
                    "but the YAML value is under springfix.email. The binder therefore does not "
                    "populate timeoutSeconds."
                ),
                confidence="high",
                evidence=[
                    EvidenceReference(
                        file="src/main/java/com/springfix/sample/config/MailProperties.java",
                        start_line=1,
                        end_line=16,
                        explanation="The class declares the springfix.mail prefix and timeoutSeconds.",
                    ),
                    EvidenceReference(
                        file="src/main/resources/application.yml",
                        start_line=1,
                        end_line=3,
                        explanation="The configured hierarchy uses springfix.email.",
                    ),
                ],
                recommended_fix="Make the Java prefix and YAML hierarchy identical, for example springfix.email.",
            )
        ],
    )


_RESPONSE_FACTORIES: dict[ProfileName, dict[type[BaseModel], Callable[[], BaseModel]]] = {
    "happy_path": {
        IssueAnalysis: _happy_path_issue,
        InvestigationPlan: _happy_path_plan,
        RootCauseAnalysis: _happy_path_rca,
    },
    "insufficient_evidence": {
        IssueAnalysis: _insufficient_issue,
        InvestigationPlan: _insufficient_plan,
        RootCauseAnalysis: _insufficient_rca,
    },
    "invalid_evidence": {
        IssueAnalysis: _happy_path_issue,
        InvestigationPlan: _happy_path_plan,
        RootCauseAnalysis: _invalid_evidence_rca,
    },
    "benchmark_transaction": {
        IssueAnalysis: _benchmark_transaction_issue,
        InvestigationPlan: _benchmark_transaction_plan,
        RootCauseAnalysis: _benchmark_transaction_rca,
    },
    "benchmark_no_unique_bean": {
        IssueAnalysis: _benchmark_bean_issue,
        InvestigationPlan: _benchmark_bean_plan,
        RootCauseAnalysis: _benchmark_bean_rca,
    },
    "benchmark_config_prefix": {
        IssueAnalysis: _benchmark_config_issue,
        InvestigationPlan: _benchmark_config_plan,
        RootCauseAnalysis: _benchmark_config_rca,
    },
}


SUPPORTED_PROFILES: tuple[ProfileName, ...] = (
    "happy_path",
    "insufficient_evidence",
    "invalid_evidence",
    "timeout",
    "invalid_json",
    "benchmark_transaction",
    "benchmark_no_unique_bean",
    "benchmark_config_prefix",
)


def get_profile_response(
    profile: ProfileName,
    response_model: type[BaseModel],
) -> BaseModel | None:
    """Return a fresh instance for the given profile and model, or None."""
    factories = _RESPONSE_FACTORIES.get(profile)
    if factories is None:
        return None
    factory = factories.get(response_model)
    if factory is None:
        return None
    return factory()


def is_failure_profile(profile: ProfileName) -> bool:
    """Return True if the profile simulates a failure (no response)."""
    return profile in ("timeout", "invalid_json")


def build_failure_exception(profile: ProfileName) -> BaseException:
    """Return the exception a failure profile should raise."""
    if profile == "timeout":
        return RetryableError("profile timeout")
    if profile == "invalid_json":
        return SchemaValidationError("profile invalid JSON")
    return SchemaValidationError(f"unknown profile {profile}")


def build_failure_trace(
    profile: ProfileName,
    *,
    node_name: str,
    prompt_chars: int,
) -> LLMCall:
    """Build a failure LLMCall record for a failure profile."""
    from datetime import UTC, datetime

    start_iso = datetime.now(tz=UTC).isoformat()
    return LLMCall(
        node=node_name,
        provider="mock",
        model=f"profile:{profile}",
        attempt=1,
        start=start_iso,
        end=start_iso,
        duration_ms=0,
        status="error",
        prompt_chars=prompt_chars,
        response_chars=0,
        input_tokens=None,
        output_tokens=None,
        error_type=type(build_failure_exception(profile)).__name__,
        error_message=str(build_failure_exception(profile))[:500],
    )
