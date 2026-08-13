package com.springfix.holdout.circularcase;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.junit.jupiter.api.Assertions.assertNull;

class CircularDependencyTest {
    @Test
    void contextShouldStartWithoutDependencyCycle() {
        new ApplicationContextRunner()
            .withUserConfiguration(Application.class)
            .run(context -> assertNull(
                context.getStartupFailure(),
                "Expected context startup to succeed, but a dependency cycle remained: "
                    + context.getStartupFailure()
            ));
    }
}
