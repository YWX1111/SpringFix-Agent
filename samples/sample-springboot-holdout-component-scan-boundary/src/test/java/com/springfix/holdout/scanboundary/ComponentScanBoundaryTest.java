package com.springfix.holdout.scanboundary;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.junit.jupiter.api.Assertions.assertNull;

class ComponentScanBoundaryTest {
    @Test
    void contextShouldStartWithReportService() {
        new ApplicationContextRunner()
            .withUserConfiguration(Application.class)
            .run(context -> assertNull(
                context.getStartupFailure(),
                "Expected component scanning to discover the report service: "
                    + context.getStartupFailure()
            ));
    }
}
