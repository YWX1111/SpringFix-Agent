package com.springfix.freshv2.h07.ingest;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.boot.test.context.ConfigDataApplicationContextInitializer;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

class TypedPropertiesTest {
    @Test
    void contextShouldBindTypedIngestSettings() {
        new ApplicationContextRunner()
            .withUserConfiguration(Application.class)
            .withInitializer(new ConfigDataApplicationContextInitializer())
            .run(context -> {
                assertNull(context.getStartupFailure(), "The ingest settings should satisfy the binding contract");
                assertEquals(2, context.getBean(IngestService.class).recipientCount());
            });
    }
}
