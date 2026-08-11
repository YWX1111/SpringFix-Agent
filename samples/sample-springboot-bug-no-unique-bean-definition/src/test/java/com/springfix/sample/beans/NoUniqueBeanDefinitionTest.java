package com.springfix.sample.beans;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.junit.jupiter.api.Assertions.assertNull;

/**
 * Gold-standard failure: context startup should succeed with one selected
 * PaymentGateway, but the sample intentionally has two candidates and no
 * @Primary or @Qualifier.
 */
class NoUniqueBeanDefinitionTest {

    @Test
    void contextShouldStartWithSinglePaymentGateway() {
        new ApplicationContextRunner()
            .withUserConfiguration(Application.class)
            .run(context -> {
                Throwable startupFailure = context.getStartupFailure();
                assertNull(
                    startupFailure,
                    "Expected startupFailure == null, but got "
                        + "NoUniqueBeanDefinitionException for PaymentGateway: "
                        + startupFailure
                );
            });
    }
}
