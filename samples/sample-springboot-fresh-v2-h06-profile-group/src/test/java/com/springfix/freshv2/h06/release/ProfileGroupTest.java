package com.springfix.freshv2.h06.release;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.boot.test.context.ConfigDataApplicationContextInitializer;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ProfileGroupTest {
    @Test
    void releaseProfileShouldActivateGroupedFeatures() {
        new ApplicationContextRunner()
            .withUserConfiguration(Application.class)
            .withInitializer(new ConfigDataApplicationContextInitializer())
            .run(context -> assertEquals(
                true,
                context.getBean(ReleaseFeatures.class).metricsEnabled(),
                "The release runtime should include its grouped feature profile"
            ));
    }
}
