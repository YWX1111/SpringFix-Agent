package com.springfix.freshv2.h02.routing;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.boot.test.context.ConfigDataApplicationContextInitializer;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

class NestedPropertiesTest {
    @Test
    void contextShouldExposeConfiguredRoutingZone() {
        new ApplicationContextRunner()
            .withUserConfiguration(Application.class)
            .withInitializer(new ConfigDataApplicationContextInitializer())
            .run(context -> {
                assertNull(context.getStartupFailure(), "The nested routing configuration should bind");
                assertEquals("https://east-router.internal", context.getBean(RoutingService.class).firstZoneUrl());
            });
    }
}
