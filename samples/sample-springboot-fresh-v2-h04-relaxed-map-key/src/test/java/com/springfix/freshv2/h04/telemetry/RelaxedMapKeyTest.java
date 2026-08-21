package com.springfix.freshv2.h04.telemetry;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.boot.test.context.ConfigDataApplicationContextInitializer;

import static org.junit.jupiter.api.Assertions.assertEquals;

class RelaxedMapKeyTest {
    @Test
    void shouldPreserveConfiguredTelemetryHeaderName() {
        new ApplicationContextRunner()
            .withUserConfiguration(Application.class)
            .withInitializer(new ConfigDataApplicationContextInitializer())
            .run(context -> assertEquals(
                "trace-123",
                context.getBean(TelemetryService.class).header("X/Trace/Id"),
                "The configured header key should remain addressable by the telemetry consumer"
            ));
    }
}
