package com.springfix.sample.config;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;

/** Gold-standard failure for a property key that does not match its prefix. */
@SpringBootTest
class ConfigurationPropertiesPrefixMismatchTest {

    @Autowired
    private MailProperties mailProperties;

    @Test
    void shouldBindConfiguredMailTimeout() {
        assertEquals(30, mailProperties.getTimeoutSeconds());
    }
}
