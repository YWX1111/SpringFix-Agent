package com.springfix.holdout.missingbean;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.junit.jupiter.api.Assertions.assertNull;

class MissingConstructorBeanTest {
    @Test
    void contextShouldStartWithAuditDependency() {
        new ApplicationContextRunner()
            .withUserConfiguration(Application.class)
            .run(context -> assertNull(
                context.getStartupFailure(),
                "Expected context startup to succeed, but the audit dependency was unresolved: "
                    + context.getStartupFailure()
            ));
    }
}
