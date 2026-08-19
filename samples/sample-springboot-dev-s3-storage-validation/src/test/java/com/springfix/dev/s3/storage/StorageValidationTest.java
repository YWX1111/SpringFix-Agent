package com.springfix.dev.s3.storage;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.ConfigDataApplicationContextInitializer;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.junit.jupiter.api.Assertions.assertNull;

class StorageValidationTest {
    @Test
    void contextShouldStartWithValidStorageSettings() {
        new ApplicationContextRunner()
            .withUserConfiguration(Application.class)
            .withInitializer(new ConfigDataApplicationContextInitializer())
            .run(context -> assertNull(
                context.getStartupFailure(),
                "Expected valid storage settings, but binding validation failed: "
                    + context.getStartupFailure()
            ));
    }
}
