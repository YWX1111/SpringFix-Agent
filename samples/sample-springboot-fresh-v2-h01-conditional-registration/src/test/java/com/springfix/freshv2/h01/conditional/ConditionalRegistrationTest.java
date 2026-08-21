package com.springfix.freshv2.h01.conditional;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

class ConditionalRegistrationTest {
    @Test
    void contextShouldProvideFeatureFlagMetrics() {
        new ApplicationContextRunner()
            .withUserConfiguration(Application.class)
            .run(context -> {
                assertNull(context.getStartupFailure(), "The application context should start");
                assertEquals(true, context.getBean(FeatureFlagMetrics.class).reportsNewCheckout());
            });
    }
}
