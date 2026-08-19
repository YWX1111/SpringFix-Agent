package com.springfix.dev.s1.shipping;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.ConfigDataApplicationContextInitializer;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ProfileConfigSourceTest {
    @Test
    void activeDevProfileShouldUseProfileSpecificShippingEndpoint() {
        new ApplicationContextRunner()
            .withUserConfiguration(Application.class)
            .withInitializer(new ConfigDataApplicationContextInitializer())
            .run(context -> assertEquals(
                "https://shipping-dev.internal",
                context.getBean(ShippingService.class).endpoint(),
                "The active dev profile must select its profile-specific shipping endpoint"
            ));
    }
}
