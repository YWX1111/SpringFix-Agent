package com.springfix.holdout.mappingconflict;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.WebApplicationContextRunner;

import static org.junit.jupiter.api.Assertions.assertNull;

class AmbiguousRequestMappingTest {
    @Test
    void contextShouldStartWithDistinctRequestMappings() {
        new WebApplicationContextRunner()
            .withUserConfiguration(Application.class)
            .run(context -> assertNull(
                context.getStartupFailure(),
                "Expected request mappings to be unambiguous: "
                    + context.getStartupFailure()
            ));
    }
}
