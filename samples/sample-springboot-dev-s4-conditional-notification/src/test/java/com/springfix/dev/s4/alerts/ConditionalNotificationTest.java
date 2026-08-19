package com.springfix.dev.s4.alerts;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.ConfigDataApplicationContextInitializer;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.junit.jupiter.api.Assertions.assertNull;

class ConditionalNotificationTest {
    @Test
    void contextShouldStartWithConfiguredNotificationProvider() {
        new ApplicationContextRunner()
            .withUserConfiguration(Application.class)
            .withInitializer(new ConfigDataApplicationContextInitializer())
            .run(context -> assertNull(
                context.getStartupFailure(),
                "Expected the configured notification provider to be available, but startup failed: "
                    + context.getStartupFailure()
            ));
    }
}
