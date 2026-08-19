package com.springfix.dev.s5.cache;

import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.ConfigDataApplicationContextInitializer;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.junit.jupiter.api.Assertions.assertEquals;

class CacheBindingKeyTest {
    @Test
    void shouldBindRegionSpecificCacheTtl() {
        new ApplicationContextRunner()
            .withUserConfiguration(Application.class)
            .withInitializer(new ConfigDataApplicationContextInitializer())
            .run(context -> assertEquals(
                Duration.ofSeconds(30),
                context.getBean(CacheService.class).ttlFor("us-east"),
                "The nested cache map must be bound from the configured property path"
            ));
    }
}
