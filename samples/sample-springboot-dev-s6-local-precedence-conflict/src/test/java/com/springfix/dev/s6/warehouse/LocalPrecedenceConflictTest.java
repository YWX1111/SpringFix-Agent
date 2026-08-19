package com.springfix.dev.s6.warehouse;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.ConfigDataApplicationContextInitializer;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.junit.jupiter.api.Assertions.assertNull;

class LocalPrecedenceConflictTest {
    @Test
    void contextShouldStartWithValidLocalRetryConfiguration() {
        new ApplicationContextRunner()
            .withUserConfiguration(Application.class)
            .withInitializer(new ConfigDataApplicationContextInitializer())
            .run(context -> assertNull(
                context.getStartupFailure(),
                "Expected valid warehouse configuration, but the higher-precedence local source failed: "
                    + context.getStartupFailure()
            ));
    }
}
