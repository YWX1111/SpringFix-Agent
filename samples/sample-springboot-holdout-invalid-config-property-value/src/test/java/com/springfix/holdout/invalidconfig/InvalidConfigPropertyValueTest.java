package com.springfix.holdout.invalidconfig;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.junit.jupiter.api.Assertions.assertNull;

class InvalidConfigPropertyValueTest {
    @Test
    void contextShouldStartWithValidBillingConfiguration() {
        new ApplicationContextRunner()
            .withUserConfiguration(Application.class)
            .run(context -> assertNull(
                context.getStartupFailure(),
                "Expected valid billing configuration, but binding failed: "
                    + context.getStartupFailure()
            ));
    }
}
