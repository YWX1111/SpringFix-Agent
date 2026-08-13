package com.springfix.holdout.profilecase;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.junit.jupiter.api.Assertions.assertNull;

class WrongActiveProfileTest {
    @Test
    void contextShouldStartWithMatchingProfile() {
        new ApplicationContextRunner()
            .withUserConfiguration(Application.class)
            .withPropertyValues("spring.profiles.active=test")
            .run(context -> assertNull(
                context.getStartupFailure(),
                "Expected profile configuration to provide the catalog: "
                    + context.getStartupFailure()
            ));
    }
}
