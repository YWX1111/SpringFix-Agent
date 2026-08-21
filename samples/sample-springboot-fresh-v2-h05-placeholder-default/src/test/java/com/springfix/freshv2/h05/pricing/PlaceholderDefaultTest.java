package com.springfix.freshv2.h05.pricing;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.boot.test.context.ConfigDataApplicationContextInitializer;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

class PlaceholderDefaultTest {
    @Test
    void contextShouldUseCurrencyFallbackWhenUnset() {
        new ApplicationContextRunner()
            .withUserConfiguration(Application.class)
            .withInitializer(new ConfigDataApplicationContextInitializer())
            .run(context -> {
                assertNull(context.getStartupFailure(), "The pricing context should start without an optional currency");
                assertEquals("USD", context.getBean(PricingService.class).currency());
            });
    }
}
