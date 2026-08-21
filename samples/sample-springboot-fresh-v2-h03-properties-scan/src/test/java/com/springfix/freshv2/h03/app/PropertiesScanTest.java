package com.springfix.freshv2.h03.app;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.boot.test.context.ConfigDataApplicationContextInitializer;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

class PropertiesScanTest {
    @Test
    void contextShouldExposeConfiguredMailRelay() {
        new ApplicationContextRunner()
            .withUserConfiguration(Application.class)
            .withInitializer(new ConfigDataApplicationContextInitializer())
            .run(context -> {
                assertNull(context.getStartupFailure(), "The mail properties should be registered");
                assertEquals("smtp.internal", context.getBean(MailService.class).relay());
            });
    }
}
